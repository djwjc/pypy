""" Try to test systematically all cases of ll_math.py.
"""

from pypy.rpython.lltypesystem.module import ll_math
from pypy.module.math.test.test_direct import MathTests, finite


class TestMath(MathTests):
    pass

def make_test_case((fnname, args, expected), dict):
    #
    def test_func(self):
        fn = getattr(ll_math, 'll_math_' + fnname)
        repr = "%s(%s)" % (fnname, ', '.join(map(str, args)))
        try:
            got = fn(*args)
        except ValueError:
            assert expected == ValueError, "%s: got a ValueError" % (repr,)
        except OverflowError:
            assert expected == OverflowError, "%s: got an OverflowError" % (
                repr,)
        else:
            if callable(expected):
                ok = expected(got)
            else:
                assert finite(expected), "badly written test"
                gotsign = ll_math.math_copysign(1.0, got)
                expectedsign = ll_math.math_copysign(1.0, expected)
                ok = finite(got) and (got == expected and
                                      gotsign == expectedsign)
            if not ok:
                raise AssertionError("%r: got %s" % (repr, got))
    #
    dict[fnname] = dict.get(fnname, 0) + 1
    testname = 'test_%s_%d' % (fnname, dict[fnname])
    test_func.func_name = testname
    setattr(TestMath, testname, test_func)

_d = {}
for testcase in TestMath.TESTCASES:
    make_test_case(testcase, _d)
