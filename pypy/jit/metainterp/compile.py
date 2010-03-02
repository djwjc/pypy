
from pypy.rpython.ootypesystem import ootype
from pypy.objspace.flow.model import Constant, Variable
from pypy.rlib.objectmodel import we_are_translated
from pypy.rlib.debug import debug_start, debug_stop
from pypy.conftest import option

from pypy.jit.metainterp.resoperation import ResOperation, rop
from pypy.jit.metainterp.history import TreeLoop, Box, History, LoopToken
from pypy.jit.metainterp.history import AbstractFailDescr, BoxInt
from pypy.jit.metainterp.history import BoxPtr, BoxObj, BoxFloat, Const
from pypy.jit.metainterp import history
from pypy.jit.metainterp.specnode import NotSpecNode, more_general_specnodes
from pypy.jit.metainterp.typesystem import llhelper, oohelper
from pypy.jit.metainterp.optimizeutil import InvalidLoop

class GiveUp(Exception):
    pass

def show_loop(metainterp_sd, loop=None, error=None):
    # debugging
    if option.view or option.viewloops:
        if error:
            errmsg = error.__class__.__name__
            if str(error):
                errmsg += ': ' + str(error)
        else:
            errmsg = None
        if loop is None: # or type(loop) is TerminatingLoop:
            extraloops = []
        else:
            extraloops = [loop]
        metainterp_sd.stats.view(errmsg=errmsg, extraloops=extraloops)

def create_empty_loop(metainterp):
    name = metainterp.staticdata.stats.name_for_new_loop()
    return TreeLoop(name)

def make_loop_token(nb_args):
    loop_token = LoopToken()
    loop_token.specnodes = [prebuiltNotSpecNode] * nb_args
    return loop_token

# ____________________________________________________________

def compile_new_loop(metainterp, old_loop_tokens, greenkey, start):
    """Try to compile a new loop by closing the current history back
    to the first operation.
    """    
    history = metainterp.history
    loop = create_empty_loop(metainterp)
    loop.greenkey = greenkey
    loop.inputargs = history.inputargs
    for box in loop.inputargs:
        assert isinstance(box, Box)
    if start > 0:
        loop.operations = history.operations[start:]
    else:
        loop.operations = history.operations
    metainterp_sd = metainterp.staticdata
    loop_token = make_loop_token(len(loop.inputargs))
    loop.token = loop_token
    loop.operations[-1].descr = loop_token     # patch the target of the JUMP
    try:
        old_loop_token = metainterp_sd.state.optimize_loop(
            metainterp_sd, old_loop_tokens, loop)
    except InvalidLoop:
        return None
    if old_loop_token is not None:
        metainterp.staticdata.log("reusing old loop")
        return old_loop_token
    send_loop_to_backend(metainterp_sd, loop, "loop")
    insert_loop_token(old_loop_tokens, loop_token)
    return loop_token

def insert_loop_token(old_loop_tokens, loop_token):
    # Find where in old_loop_tokens we should insert this new loop_token.
    # The following algo means "as late as possible, but before another
    # loop token that would be more general and so completely mask off
    # the new loop_token".
    for i in range(len(old_loop_tokens)):
        if more_general_specnodes(old_loop_tokens[i].specnodes,
                                  loop_token.specnodes):
            old_loop_tokens.insert(i, loop_token)
            break
    else:
        old_loop_tokens.append(loop_token)

def send_loop_to_backend(metainterp_sd, loop, type):
    globaldata = metainterp_sd.globaldata
    loop_token = loop.token
    loop_token.number = n = globaldata.loopnumbering
    globaldata.loopnumbering += 1

    metainterp_sd.logger_ops.log_loop(loop.inputargs, loop.operations, n, type)
    if not we_are_translated():
        show_loop(metainterp_sd, loop)
        loop.check_consistency()
    metainterp_sd.profiler.start_backend()
    debug_start("jit-backend")
    try:
        metainterp_sd.cpu.compile_loop(loop.inputargs, loop.operations,
                                       loop.token)
    finally:
        debug_stop("jit-backend")
    metainterp_sd.profiler.end_backend()
    metainterp_sd.stats.add_new_loop(loop)
    if not we_are_translated():
        if type != "entry bridge":
            metainterp_sd.stats.compiled()
        else:
            loop._ignore_during_counting = True
    metainterp_sd.log("compiled new " + type)

def send_bridge_to_backend(metainterp_sd, faildescr, inputargs, operations):
    n = metainterp_sd.cpu.get_fail_descr_number(faildescr)
    metainterp_sd.logger_ops.log_bridge(inputargs, operations, n)
    if not we_are_translated():
        show_loop(metainterp_sd)
        TreeLoop.check_consistency_of(inputargs, operations)
        pass
    metainterp_sd.profiler.start_backend()
    debug_start("jit-backend")
    try:
        metainterp_sd.cpu.compile_bridge(faildescr, inputargs, operations)
    finally:
        debug_stop("jit-backend")
    metainterp_sd.profiler.end_backend()
    if not we_are_translated():
        metainterp_sd.stats.compiled()
    metainterp_sd.log("compiled new bridge")            

# ____________________________________________________________

class _DoneWithThisFrameDescr(AbstractFailDescr):
    pass

class DoneWithThisFrameDescrVoid(_DoneWithThisFrameDescr):
    def handle_fail(self, metainterp_sd):
        assert metainterp_sd.result_type == 'void'
        raise metainterp_sd.DoneWithThisFrameVoid()

class DoneWithThisFrameDescrInt(_DoneWithThisFrameDescr):
    def handle_fail(self, metainterp_sd):
        assert metainterp_sd.result_type == 'int'
        result = metainterp_sd.cpu.get_latest_value_int(0)
        raise metainterp_sd.DoneWithThisFrameInt(result)

class DoneWithThisFrameDescrRef(_DoneWithThisFrameDescr):
    def handle_fail(self, metainterp_sd):
        assert metainterp_sd.result_type == 'ref'
        cpu = metainterp_sd.cpu
        result = cpu.get_latest_value_ref(0)
        raise metainterp_sd.DoneWithThisFrameRef(cpu, result)

class DoneWithThisFrameDescrFloat(_DoneWithThisFrameDescr):
    def handle_fail(self, metainterp_sd):
        assert metainterp_sd.result_type == 'float'
        result = metainterp_sd.cpu.get_latest_value_float(0)
        raise metainterp_sd.DoneWithThisFrameFloat(result)

class ExitFrameWithExceptionDescrRef(_DoneWithThisFrameDescr):
    def handle_fail(self, metainterp_sd):
        cpu = metainterp_sd.cpu
        value = cpu.get_latest_value_ref(0)
        raise metainterp_sd.ExitFrameWithExceptionRef(cpu, value)


prebuiltNotSpecNode = NotSpecNode()

class TerminatingLoopToken(LoopToken):
    terminating = True
    
    def __init__(self, nargs, finishdescr):
        self.specnodes = [prebuiltNotSpecNode]*nargs
        self.finishdescr = finishdescr

def make_done_loop_tokens():
    done_with_this_frame_descr_void = DoneWithThisFrameDescrVoid()
    done_with_this_frame_descr_int = DoneWithThisFrameDescrInt()
    done_with_this_frame_descr_ref = DoneWithThisFrameDescrRef()
    done_with_this_frame_descr_float = DoneWithThisFrameDescrFloat()
    exit_frame_with_exception_descr_ref = ExitFrameWithExceptionDescrRef()

    # pseudo loop tokens to make the life of optimize.py easier
    return {'loop_tokens_done_with_this_frame_int': [
                TerminatingLoopToken(1, done_with_this_frame_descr_int)
                ],
            'loop_tokens_done_with_this_frame_ref': [
                TerminatingLoopToken(1, done_with_this_frame_descr_ref)
                ],
            'loop_tokens_done_with_this_frame_float': [
                TerminatingLoopToken(1, done_with_this_frame_descr_float)
                ],
            'loop_tokens_done_with_this_frame_void': [
                TerminatingLoopToken(0, done_with_this_frame_descr_void)
                ],
            'loop_tokens_exit_frame_with_exception_ref': [
                TerminatingLoopToken(1, exit_frame_with_exception_descr_ref)
                ],
            }

class ResumeDescr(AbstractFailDescr):
    def __init__(self, original_greenkey):
        self.original_greenkey = original_greenkey

class ResumeGuardDescr(ResumeDescr):
    counter = 0
    # this class also gets attributes stored by resume.py code

    def __init__(self, metainterp_sd, original_greenkey):
        ResumeDescr.__init__(self, original_greenkey)
        self.metainterp_sd = metainterp_sd

    def store_final_boxes(self, guard_op, boxes):
        guard_op.fail_args = boxes
        self.guard_opnum = guard_op.opnum

    def handle_fail(self, metainterp_sd):
        from pypy.jit.metainterp.pyjitpl import MetaInterp
        metainterp = MetaInterp(metainterp_sd)
        return metainterp.handle_guard_failure(self)

    def compile_and_attach(self, metainterp, new_loop):
        # We managed to create a bridge.  Attach the new operations
        # to the corrsponding guard_op and compile from there
        inputargs = metainterp.history.inputargs
        if not we_are_translated():
            self._debug_suboperations = new_loop.operations
        send_bridge_to_backend(metainterp.staticdata, self, inputargs,
                               new_loop.operations)


class ResumeGuardForcedDescr(ResumeGuardDescr):

    def handle_fail(self, metainterp_sd):
        from pypy.jit.metainterp.pyjitpl import MetaInterp
        metainterp = MetaInterp(metainterp_sd)
        token = metainterp_sd.cpu.get_latest_force_token()
        data = self.fetch_data(token)
        if data is None:
            data = []
        metainterp._already_allocated_resume_virtuals = data
        self.counter = -2     # never compile
        return metainterp.handle_guard_failure(self)

    def force_virtualizable(self, vinfo, virtualizable, force_token):
        from pypy.jit.metainterp.pyjitpl import MetaInterp
        from pypy.jit.metainterp.resume import force_from_resumedata
        metainterp = MetaInterp(self.metainterp_sd)
        metainterp.history = None    # blackholing
        liveboxes = metainterp.cpu.make_boxes_from_latest_values(self)
        virtualizable_boxes, data = force_from_resumedata(metainterp,
                                                          liveboxes, self)
        vinfo.write_boxes(virtualizable, virtualizable_boxes)
        self.save_data(force_token, data)

    def save_data(self, key, value):
        globaldata = self.metainterp_sd.globaldata
        assert key not in globaldata.resume_virtuals
        globaldata.resume_virtuals[key] = value

    def fetch_data(self, key):
        globaldata = self.metainterp_sd.globaldata
        assert key in globaldata.resume_virtuals
        data = globaldata.resume_virtuals[key]
        del globaldata.resume_virtuals[key]
        return data


class ResumeFromInterpDescr(ResumeDescr):
    def __init__(self, original_greenkey, redkey):
        ResumeDescr.__init__(self, original_greenkey)
        self.redkey = redkey

    def compile_and_attach(self, metainterp, new_loop):
        # We managed to create a bridge going from the interpreter
        # to previously-compiled code.  We keep 'new_loop', which is not
        # a loop at all but ends in a jump to the target loop.  It starts
        # with completely unoptimized arguments, as in the interpreter.
        metainterp_sd = metainterp.staticdata
        metainterp.history.inputargs = self.redkey
        new_loop_token = make_loop_token(len(self.redkey))
        new_loop.greenkey = self.original_greenkey
        new_loop.inputargs = self.redkey
        new_loop.token = new_loop_token
        send_loop_to_backend(metainterp_sd, new_loop, "entry bridge")
        # send the new_loop to warmspot.py, to be called directly the next time
        metainterp_sd.state.attach_unoptimized_bridge_from_interp(
            self.original_greenkey,
            new_loop_token)
        # store the new loop in compiled_merge_points too
        glob = metainterp_sd.globaldata
        old_loop_tokens = glob.get_compiled_merge_points(
            self.original_greenkey)
        # it always goes at the end of the list, as it is the most
        # general loop token
        old_loop_tokens.append(new_loop_token)


def compile_new_bridge(metainterp, old_loop_tokens, resumekey):
    """Try to compile a new bridge leading from the beginning of the history
    to some existing place.
    """    
    # The history contains new operations to attach as the code for the
    # failure of 'resumekey.guard_op'.
    #
    # Attempt to use optimize_bridge().  This may return None in case
    # it does not work -- i.e. none of the existing old_loop_tokens match.
    new_loop = create_empty_loop(metainterp)
    new_loop.inputargs = metainterp.history.inputargs
    new_loop.operations = metainterp.history.operations
    metainterp_sd = metainterp.staticdata
    try:
        target_loop_token = metainterp_sd.state.optimize_bridge(metainterp_sd,
                                                                old_loop_tokens,
                                                                new_loop)
    except InvalidLoop:
        return None
    # Did it work?
    if target_loop_token is not None:
        # Yes, we managed to create a bridge.  Dispatch to resumekey to
        # know exactly what we must do (ResumeGuardDescr/ResumeFromInterpDescr)
        prepare_last_operation(new_loop, target_loop_token)
        resumekey.compile_and_attach(metainterp, new_loop)
    return target_loop_token

def prepare_last_operation(new_loop, target_loop_token):
    op = new_loop.operations[-1]
    if not isinstance(target_loop_token, TerminatingLoopToken):
        # normal case
        op.descr = target_loop_token     # patch the jump target
    else:
        # The target_loop_token is a pseudo loop token,
        # e.g. loop_tokens_done_with_this_frame_void[0]
        # Replace the operation with the real operation we want, i.e. a FINISH
        descr = target_loop_token.finishdescr
        new_op = ResOperation(rop.FINISH, op.args, None, descr=descr)
        new_loop.operations[-1] = new_op
