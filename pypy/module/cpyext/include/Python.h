#ifndef Py_PYTHON_H
#define Py_PYTHON_H

typedef struct _object {
    long refcnt;
} PyObject;

#include <stdio.h>

#include "floatobject.h"
#include "methodobject.h"

#include "modsupport.h"
#include "pythonrun.h"

#endif
