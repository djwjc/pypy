from pypy.rpython.lltypesystem import rffi, lltype
from pypy.module.cpyext.api import cpython_api

@cpython_api([], rffi.INT_real)
def Py_IsInitialized(space):
    return 1
