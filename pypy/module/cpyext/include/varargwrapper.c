#include <pypy_rename.h>
#include <Python.h>
#include <stdarg.h>

PyObject * PyPyTuple_Pack(Py_ssize_t size, ...)
{
    va_list ap;
    PyObject *cur, *tuple;
    int i;

    tuple = PyTuple_New(size);
    va_start(ap, size);
    for (i = 0; i < size; cur = va_arg(ap, PyObject*), i++) {
        Py_INCREF(cur);
        if (PyTuple_SetItem(tuple, i, cur) < 0)
            return NULL;
    }
    va_end(ap);
    return tuple;
}

