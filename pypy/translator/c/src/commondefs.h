
/************************************************************/
 /***  C header subsection: common types and macros        ***/


/* We only support the following two kinds of platform:

                 int     long     long long     void*
   --32-bit--    32      32         64          32
   --64-bit--    32      64         64          64

   In particular, Win64 is not supported because it has sizeof(long) == 4.
   To fix this, find and review all the places that cast a pointer to a long.
*/

#include <limits.h>

#if INT_MAX != 2147483647
#  error "unsupported value for INT_MAX"
#endif
#if INT_MIN != -2147483647-1
#  error "unsupported value for INT_MIN"
#endif

#if LLONG_MAX != 9223372036854775807LL
#  error "unsupported value for LLONG_MAX"
#endif
#if LLONG_MIN != -9223372036854775807LL-1LL
#  error "unsupported value for LLONG_MIN"
#endif


/******************** 32-bit support ********************/
#if PYPY_LONG_BIT == 32

#  if LONG_MAX != 2147483647L
#    error "error in LONG_MAX (32-bit sources but a 64-bit compiler?)"
#  endif
#  if LONG_MIN != -2147483647L-1L
#    error "unsupported value for LONG_MIN"
#  endif

#  define SIZEOF_INT        4
#  define SIZEOF_LONG       4
#  define SIZEOF_LONG_LONG  8

/******************** 64-bit support ********************/
#else

#  if LONG_MAX != 9223372036854775807L
#    error "error in LONG_MAX (64-bit sources but a 32-bit compiler?)"
#  endif
#  if LONG_MIN != -9223372036854775807L-1L
#    error "unsupported value for LONG_MIN"
#  endif

#  define SIZEOF_INT        4
#  define SIZEOF_LONG       8
#  define SIZEOF_LONG_LONG  8

#endif

/********************************************************/

typedef long Py_intptr_t;
typedef unsigned long Py_uintptr_t;

#if ((-1) >> 1) > 0
#  define Py_ARITHMETIC_RIGHT_SHIFT(TYPE, I, J) \
	  ((I) < 0 ? -1-((-1-(I)) >> (J)) : (I) >> (J))
#elif ((-1) >> 1) == -1
#  define Py_ARITHMETIC_RIGHT_SHIFT(TYPE, I, J) ((I) >> (J))
#else
#  error "uh? strange result"
#endif

#define HAVE_LONG_LONG 1
#define Py_HUGE_VAL HUGE_VAL
