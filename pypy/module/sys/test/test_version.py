from pypy.module.sys.version import rev2int

def test_rev2int():
    assert rev2int("71630") == 71630
    assert rev2int("") == 0
