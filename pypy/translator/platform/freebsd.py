
import py, os
from pypy.translator.platform import posix

class FreeBSD(posix.BasePosix):
    name = "freebsd"

    link_flags = ['-pthread', '-L/usr/local/lib']
    cflags = ['-O3', '-pthread', '-fomit-frame-pointer', '-I/usr/local/include']
    standalone_only = []
    shared_only = []
    so_ext = 'so'
    make_cmd = 'gmake'

    def _args_for_shared(self, args):
        return ['-shared'] + args

    def include_dirs_for_libffi(self):
        return ['/usr/local/include']

    def library_dirs_for_libffi(self):
        return ['/usr/local/lib']

class FreeBSD_64(FreeBSD):
    shared_only = ['-fPIC']
