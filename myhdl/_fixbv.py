#  This file is part of the myhdl library, a Python package for using
#  Python as a Hardware Description Language.
#
#  Copyright (C) 2003-2013 Jan Decaluwe
#
#  The myhdl library is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public License as
#  published by the Free Software Foundation; either version 2.1 of the
#  License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful, but
#  WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.

#  You should have received a copy of the GNU Lesser General Public
#  License along with this library; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

""" Module with the intbv class """

from math import floor, ceil, log
import operator

from myhdl._compat import integer_types, string_types, builtins
from myhdl._bin import bin
from myhdl._intbv import intbv

# Introduction
# -------------------------------------------------------
# Any fixed-point is a scaled integer, and can therefore be represented by a integer-value and a scaling factor,
# where the scaling-factor must be a integer-power of 2: scaling-factor = 2^shift, where the shift-factor can be any
# integer value (positive and negative). The shift factor is related to the fractionlength by the relation:
# fractionlength=-shift.
# By definition: RealWorldValue = StoredInteger * 2**shift
#
# Because a fixed-point number is a scaled integer, all fixed-point numbers lie on a 'grid' determined by the
# shift-factor. When the fixbv is initialized, the initialization-value might not lie on the grid. When this happens, the
# initialization-value is rounded to the nearest grid-point. The same holds for the 'min'- and 'max'-value.
#
# Eventhough all operations are performed in full-precision, without overflow handling or rounding, the 'min'- and 'max'-value
# can be provided. These values are used to determine the number of bits (nrbits) and when assigning the fixbv to a Signal.next 
# 'register'. During this assignment, the selected rounding mode and overflow mode is used (TODO: to be implemented).

# Guidelines
# -------------------------------------------------------
# * Precision:
#    Because (a) every fixed-point number is represented by an stored-integer and (b) python can handle integers of
#    infinite length, all operations within the fixbv-class can be (and are!) done with infinite precision.
#    Casting the fixbv to a float, might therefore cause for round-off errors or over-/underflow errors.
# * Quantization and overflow handling
#    The fixbv-class will do all operations in full-precision, therefore quantization and overflow handling will not be done.
#    These operations only make sense when the actual number is stored into a register. Therefore this should be handled by the
#    Signal-class. Unfortunately this choice was not made. Therefore the following behavior is used:
#     * at initialization: the min/max and nrbits values are optional, unless it is used to initiate a Signal, then it
#       is mandatory
#     * After any operation (add/sub/mult/etc) a fixbv without these fields, will be returned. This is done because one
#       can only make worstcase estimates about the min/max value and the nr-bits. Internal arithmetic is infinite
#       precision, the rounding and overflowhandling will be handled at assignment to Signal.next

#
# Food for thought:
#----------------------
# * Initialization:
#    When a floating-point-value is used as init-value, the shift-value is used to create a stored-integer-value. In this
#    process the nearest integer is taken, thus a round-to-nearest scheme is used. (TODO: to be implemented)
# * Division:
#    In principle divisions are not defined for integers (and therefore also not for fixed-point-numbers), because N/K
#    does not result in an integer for all N and K combinations.
#    Python makes a distinction between a true-division and a floor-division. A true-division is what we normally use in
#    a mathematical operations in the real-world. The floor-division rounds the true-division to the integer
#    closest to -infinity. Because of potential accuracy problems, it is chosen to not implement the true-division and
#    let the user make the right decisions.
# * Fraction-length and Word-length
#    the fraction-length equals -shift. The word-length is not known by the fixbv, since no overflow or quantization
#    will be performed. All operations are done in infinite precision and therefore overflow-handling and quantization
#    are not needed.

def alignvalues(a, b):
    # Example: a=100*2^10, b=10*2^2
    # After alignment, the values become: a' = 25600 * 2^2 and b'=b
    # This operation must happen without loss of resolution, which means that all values must remain integer at all time.

    assert isinstance(a, tuple) and len(a) == 2, 'It is assumed that the first input it a tuple of length 2'
    assert isinstance(b, tuple) and len(b) == 2, 'It is assumed that the second input it a tuple of length 2'
    a_val = a[0]
    a_shift = a[1]
    b_val = b[0]
    b_shift = b[1]

    if a_shift >= b_shift:
        diff_shift = a_shift - b_shift
        a_val = a_val * 2**diff_shift
        a_shift = b_shift
        return (a_val, a_shift),(b_val, b_shift)
    else:
        b, a = alignvalues(b, a)
        return a, b

def calc_nr_bits(val):
    if val == 0:
        a = 0
        nrbits = int(0)        # A bit arbitrary value; I chose to use same behavior as bit_length()-function
    elif val < 0:
        a = len(bin(val))
        nrbits = int(ceil(log(-val, 2)) + 1)
    else:
        a = len(bin(val)) + 1
        nrbits = int(ceil(log(val + 1, 2)) + 1)
    return nrbits

def fixbvstr_from_tuple(si, shift):
    return '%d * 2**%d' % (si, shift)

class fixbv(object):
    # ------------------------------------------------------------------------------
    #                          GENERIC CLASS-METHODS
    # ------------------------------------------------------------------------------
    #
    # function : __init__
    # brief    : initializes the fixbv
    # input    :
    #       val stored-integer value
    #       shift shift-value
    #       min minimum-value of the stored-integer
    #       max maximum-value of the stored-integer
    def __init__(self, val=0, shift=0, min=None, max=None, asfloat=False):
        assert (min is None and max is None) or \
               (min is not None and max is not None), \
               'Expected either min AND max equal to None or min and max not equal to None'
        assert isinstance(shift, integer_types), 'shift must be an integer'
        if isinstance(asfloat, (list, tuple)):
            self._init_asfloat = bool(asfloat[0])
            self._print_asfloat = bool(asfloat[1])
            self._vcd_asfloat = bool(asfloat[2])
        else:
            self._init_asfloat = bool(asfloat)
            self._print_asfloat = bool(asfloat)
            self._vcd_asfloat = bool(asfloat)
            self._shift = 0
            self._val = 0
            self._min = None
            self._max = None
        if isinstance(val, fixbv):
            self._shift = val._shift
            self._val = val._val
            self._min = val._min
            self._max = val._max
        else:
            self._shift = shift
            self._val = self._cast(val)
            self._min = self._cast(min)
            self._max = self._cast(max)
            if max is not None:
                assert self._min < self._max, 'Exptected min < max, but got min={} and max={} instead'.format(min, max)
        self._handleBounds()
    #__slots__ = ('_val', '_min', '_max', _shift'_handleBounds')

    # ------------------------------------------------------------------------------
    #                          ATTRIBUTES
    # ------------------------------------------------------------------------------
    #_val = 0            # the stored integer value
    #_shift = 0          # the shift value to obtain a real-world value
    #_min = None
    #_max = None

    # ------------------------------------------------------------------------------
    #                          PROPERTIES
    # ------------------------------------------------------------------------------
    # create the properties:
    #   * maxfloat       - the maximum value as integer (when the value does not have a fraction) or floating point number (when the value has a fraction)
    #   * minfloat       - the minimum value as integer (when the value does not have a fraction) or floating point number (when the value has a fraction)
    #   * maxsi          - the stored integer part of the maximum value
    #   * minsi          - the stored integer part of the minimum value
    #   * si             - stored integer value
    #   * shift          - shift value to obtain a real-world value
    #   * fractionlength - number of bits before/after the binary point
    #   * nrbits         - number of bits needed to store the value, is calculated based on maxsi and minsi. Returns 0 when either is not set.
    @property
    def maxfloat(self):
        return self.maxsi * 2**self.shift

    @property
    def minfloat(self):
        return self.minsi * 2**self.shift

    def getsi(self):
        return self._val
    def setsi(self, val):
        self._val = int(val)
    si = property(getsi, setsi)

    def getshift(self):
        return self._shift
    shift = property(getshift) # read only!

    def getfractionlength(self):
        return -self.shift
    fractionlength = property(getfractionlength)

    def getminsi(self):
        return self._min
    def setminsi(self, minsi):
        self._min = self._cast(minsi)
    minsi = property(getminsi, setminsi)

    def getmaxsi(self):
        return self._max
    def setmaxsi(self, maxsi):
        self._max = self._cast(maxsi)
    maxsi = property(getmaxsi, setmaxsi)

    def getnrbits(self):
        if self.minsi is None:
            return 0
        else:
            NrBitsMin = calc_nr_bits(self.minsi)
            NrBitsMax = calc_nr_bits(self.maxsi-1)
            return max(NrBitsMin, NrBitsMax)
    nrbits = property(getnrbits)

    def _cast(self, val):
        if isinstance(val, float):
            if self._init_asfloat:
                return int(floor(val * 2**(-self.shift) + 0.5)) # cast from float
            else:
                raise TypeError('fixbv does not accept floats by default, maybe you want to use asfloat=True')
        if val is None:
            return None # allow None
        return int(val) # e.g. string '0x3a'
           
    def fixto(self, other):
        
        if isinstance(other, fixbv):
            shift2 = other.shift
        elif hasattr(other, '_val') and isinstance(other._val, fixbv):
            shift2 = other._val.shift
        else:
            raise Exception('fixto only accepts fixbv')
        sh = self.shift - shift2      
        if sh >= 0:
            si = self.si * 2**sh
        else:
            si = self.si // (2**-sh) # truncate
        return fixbv(si, shift2)  

    #
    # function : _isfixbv
    # brief    : Check if the 'other' is a fixbv or a signal containing a fixbv, return true is this
    #            is the case
    #
    def _isfixbv(self, other):
        if isinstance(other, fixbv):
            return True
        if hasattr(other, '_val'):
            if isinstance(other._val, fixbv):
                return True
        return False

    def eps(self):
        # returns the value of 1 LSB, the resolution of the real-world-value
        return 2**self.shift

    #
    # function : align
    # brief    : Align the input variable "val" to the fixbv object. This
    #            function supports different input types:
    #            o fixbv
    #            o intbv
    #            o integer
    #            o float
    #
    def align(self, other):
        # This function aligns the fixbv 'self' and 'other', such that they have the same shift factor.
        # The function returns two fixbv-objects.
        if isinstance(other, fixbv):
            a = (self.si, self.shift)
            b = (other.si, other.shift)
            (c, d) = alignvalues(a, b)
            x = fixbv(c[0], c[1])
            y = fixbv(d[0], d[1])
            return (x, y)
        else:
            x = fixbv(other)
            return self.align(x)

    def _handleBounds(self):
        # either _min AND _max are None, or both are not None
        if  self.maxsi is not None and self.minsi is not None:
            if (self.minsi > self.si) or (self.si >= self.maxsi):
                Ssi = fixbvstr_from_tuple(self.si, self.shift)
                raise ValueError("fixbv: Value {} out of range [{}, {}>".format(Ssi, self.minsi, self.maxsi))

    # def _hasFullRange(self):
    #     min, max = self.minsi, self.maxsi
    #     if max <= 0:
    #         return False
    #     if min not in (0, -max):
    #         return False
    #     return max & max-1 == 0

    # hash
    def __hash__(self):
        raise TypeError("fixbv objects are unhashable")
        
    # copy methods
    def __copy__(self):
        c = fixbv(self.si, self.shift, self.minsi, self.maxsi)
        return c

    def __deepcopy__(self, memo):
        c = fixbv(self.si, self.shift, self.minsi, self.maxsi)
        return c

    # logical testing
    def __bool__(self):
        return bool(self.si)

    __nonzero__ = __bool__

    # length
    def __len__(self):
        return self.nrbits

    def is_integer(self):
        if self.shift >= 0:
            return True
        else:
            return (self._val % (2**-self.shift)) == 0
#            binstr = bin(self.si)
#            binstr_reversed = binstr[::-1]
#            nr_leading_zeros = len(binstr_reversed) - len(binstr_reversed.lstrip('0'))
#            #print "Leading zeros", nr_leading_zeros
#            if nr_leading_zeros + self.shift >= 0:
#                return True
#            else:
#                return False

    #------------------------------------------------------------------------------
    #                          INDEXING AND SLICING METHODS
    #------------------------------------------------------------------------------
    def __iter__(self):
        if not self.nrbits:
            raise TypeError("Cannot iterate over unsized fixbv")
        return iter([self[i+self.shift] for i in range(self.nrbits-1, -1, -1)])

    def __getitem__(self, key):
        if isinstance(key, slice):
            i, j = key.start-self.shift, key.stop-self.shift
            if j is None: # default
                j = self.shift
            j = int(j)
            if j < 0:
                raise ValueError("fixbv[i:j] requires j >= {}\n" \
                      "            j == {}".format(self.shift, j))
            if i is None: # default
                return intbv(self.si >> j)
            i = int(i)
            if i <= j:
                raise ValueError("fixbv[i:j] requires i > j\n" \
                      "            i, j == {}, {}".format(i, j))
            res = intbv((self.si & (int(1) << i)-1) >> j, _nrbits=i-j)
            return res
        else:
            i = int(key-self.shift)
            res = bool((self.si >> i) & 0x1)
            return res

    def __setitem__(self, key, val):
        # convert val to int to avoid confusion with intbv or Signals
        val = int(val)
        if isinstance(key, slice):
            i, j = key.start, key.stop
            if j is None: # default
                j = 0
            j = int(j)
            if j < 0:
                raise ValueError("fixbv[i:j] = v requires j >= 0\n" \
                      "            j == %s" % j)
            if i is None: # default
                q = self.si % (int(1) << j)
                self.si = val * (int(1) << j) + q
                self._handleBounds()
                return
            i = int(i)
            if i <= j:
                raise ValueError("fixbv[i:j] = v requires i > j\n" \
                      "            i, j, v == %s, %s, %s" % (i, j, val))
            lim = (int(1) << (i-j))
            if val >= lim or val < -lim:
                raise ValueError("fixbv[i:j] = v abs(v) too large\n" \
                      "            i, j, v == %s, %s, %s" % (i, j, val))
            mask = (lim-1) << j
            self.si &= ~mask
            self.si |= (val << j)
            self._handleBounds()
        else:
            i = int(key)
            if val == 1:
                self.si |= (int(1) << i)
            elif val == 0:
                self.si &= ~(int(1) << i)
            else:
                raise ValueError("fixbv[i] = v requires v in (0, 1)\n" \
                      "            i == %s " % i)
               
            self._handleBounds()

    def __index__(self):
        return int(self)

    #------------------------------------------------------------------------------
    #                          ARITHMETIC OPERATIONS
    #------------------------------------------------------------------------------
    def __add__(self, other):
        if self._isfixbv(other):
            (c, d) = self.align(other)
            return fixbv(c.si + d.si, c.shift)
        else:
            x = fixbv(other)
            return self + x

    __radd__=__add__
    
    def __sub__(self, other):
        if self._isfixbv(other):
            (c, d) = self.align(other)
            return fixbv(c.si - d.si, c.shift)
        else:
            x = fixbv(other)
            return self - x

    def __rsub__(self, other):
        # other will never be a fixbv, therefore cast it to s fixbv and subtract again.
        x = fixbv(other)
        return x - self

    def __mul__(self, other):
        if self._isfixbv(other):
            return fixbv(self.si * other.si, self.shift + other.shift)
        else:
            x = fixbv(other)
            return self * x

    __rmul__=__mul__
    
    def __truediv__(self, other):
        # # The result is either stored in an integer or in a floating point data-type.
        # # To achieve highest accuracy, the integer parts are treated separately from the shift-factors.
        # if self._isfixbv(other):
        #     return (self.si / other.si) * 2**(self.shift - other.shift)
        # else:
        #     x = fixbv(other)
        #     return self / x

        # The result might be very inprecise, depending on the values of a and b. 
        # Therefore it is chosen not to support this function for now.
        raise NotImplementedError('The truediv function is not implemented yet')

    def __rtruediv__(self, other):
        x = fixbv(other)
        return x / self

    def __floordiv__(self, other):
        if self._isfixbv(other):
            (c, d) = self.align(other)
            return fixbv(c.si // d.si, 0)
        else:
            x = fixbv(other)
            return self // x

    def __rfloordiv__(self, other):
        if isinstance(other, intbv):
            return int(float(other._val) // float(self.si*2**self.shift))
        else:
            return int(float(other) // float(self.si*2**self.shift))
        
    def __mod__(self, other):
        if self._isfixbv(other):
            (c,d) = self.align(other)
            return fixbv(c.si % d.si, c.shift)
        else:
            x = fixbv(other)
            return self % x

    def __rmod__(self, other):
        x = fixbv(other)
        return x % self

    def __pow__(self, other):
        # other must be an integer value
        if isinstance(other, float):
            if not other.is_integer():
                raise TypeError('Second argument must be an integer value')
        elif self._isfixbv(other):
            if not other.is_integer():
                raise TypeError('Second argument must be an integer value')
        elif not isinstance(other, intbv) and not isinstance(other, integer_types):
            raise TypeError('Second argument must be an integer value')
        powerval = int(other)
        return fixbv(self.si**powerval, self.shift * powerval)

    def __rpow__(self, other):
        raise NotImplementedError('the rpow-function is not yet implemented')

    def __iadd__(self, other):
        # FIXME: change implementation, because result should be stored in self (not in 'result')
        result = self.__add__(other)
        result._handleBounds()
        return result

    def __isub__(self, other):
        # FIXME: change implementation, because result should be stored in self (not in 'result')
        result = self.__sub__(other)
        result._handleBounds()
        return result

    def __imul__(self, other):
        # FIXME: change implementation, because result should be stored in self (not in 'result')
        result = self.__mul__(other)
        result._handleBounds()
        return result

    def __ifloordiv__(self, other):
        # FIXME: change implementation, because result should be stored in self (not in 'result')
        result = self.__floordiv__(other)
        result._handleBounds()
        return result

    def __idiv__(self, other):
        raise TypeError("fixbv: Augmented classic division not supported")

    def __itruediv__(self, other):
        raise TypeError("fixbv: Augmented true division not supported")

    def __imod__(self, other):
        # FIXME: change implementation, because result should be stored in self (not in 'result')
        result = self.__mod__(other)
        result._handleBounds()
        return result

    def __neg__(self):
        return fixbv(-self.si, self.shift)

    def __pos__(self):
        return fixbv(self.si, self.shift)

    def __abs__(self):
        return fixbv(abs(self.si), self.shift)

    #------------------------------------------------------------------------------
    #                          BITWISE OPERATIONS
    #------------------------------------------------------------------------------
    # The functions AND, OR and XOR will not be implemented, because the functionality highly depends on the users expectation:
    # * Some users might expect the function to operate on the stored integer
    # * Some users might expect the function to operate on the RW-value
    # To avoid confusion, it is better to let the user decide what to do:
    # * get the stored integers and apply the function
    # * Cast to a long (with possible quantization effects) and apply the function

    def __lshift__(self, other):
        if self._isfixbv(other):
            if other.is_integer():
                return fixbv(self.si, self.shift + int(other))
            else:
                raise TypeError("Cannot shift value by an none-integer value")
        else:
            x = fixbv(other)
            return self << x

    def __rlshift__(self, other):
        x = fixbv(other)
        return x << self

    def __rshift__(self, other):
        if self._isfixbv(other):
            if other.is_integer():
                return fixbv(self.si, self.shift - int(other))
            else:
                raise TypeError("Cannot shift value by an none-integer value")
        else:
            x = fixbv(other)
            return self >> x

    def __rrshift__(self, other):
        x = fixbv(other)
        return x >> self

    def __ilshift__(self, other):
        # The ilshift will operate on the si itself. Because of this, there might be rounding errors
        if self._isfixbv(other):
            if other.is_integer():
                self.si = int(self.si << int(other))
            else:
                raise TypeError("Cannot shift value by an none-integer value")
        else:
            x = fixbv(other)
            self <<= x

        self._handleBounds()
        return self

    def __irshift__(self, other):
        # The irshift will operate on the si itself. Because of this, there might be rounding errors
        if self._isfixbv(other):
            if other.is_integer():
                self.si = int(self.si >> int(other))
            else:
                raise TypeError("Cannot shift value by an none-integer value")
        else:
            x = fixbv(other)
            self >>= x

        self._handleBounds()
        return self

    def __invert__(self):
        if self.nrbits and self.minsi >= 0:
            return type(self)(~self.si & (int(1) << self.nrbits)-1)
        else:
            return type(self)(~self.si)

    # ------------------------------------------------------------------------------
    #                          COMPARISONS
    # ------------------------------------------------------------------------------
    def __eq__(self, other):
        # Only fixbv's can be compared in full-precision.
        # Other types are converted to fixbv first.
        if self._isfixbv(other):
            (c, d) = self.align(other)
            return (c.si == d.si) # and (c.shift == d.shift)
        else:
            other_fixbv = fixbv(other)  # convert to fixbv
            return self == other_fixbv

    def __ne__(self, other):
        return not self == other

    def __lt__(self, other):
        if self._isfixbv(other):
            (c, d) = self.align(other)
            return c.si < d.si
        else:
            other_fixbv = fixbv(other)
            return self < other_fixbv

    def __le__(self, other):
        if self._isfixbv(other):
            (c, d) = self.align(other)
            return c.si <= d.si
        else:
            other_fixbv = fixbv(other)
            return self <= other_fixbv

    def __gt__(self, other):
        return not self <= other

    def __ge__(self, other):
        return not self < other

    #------------------------------------------------------------------------------
    #                          REPRESENTATION
    #------------------------------------------------------------------------------
    def __float__(self):
        return float(self.si*2**self.shift)

    def __int__(self):
        return int(self.si*2**self.shift)
    
    def __long__(self):
        return int(self.si*2**self.shift)

    def __oct__(self):
        return oct(int(self))

    def __hex__(self):
        return hex(int(self))

    def __str__(self):
        if self._print_asfloat:
            S = "{}".format(self.si*2**self.shift)
        else:
            S = fixbvstr_from_tuple(self.si, self.shift)
        return S
    
    def __repr__(self):
        '''return string should result in exact same object'''
        if self.minsi is None:
            return "fixbv({}, {})".format(self.si, self.shift)
        else:
            return "fixbv({}, {}, min={}, max={})".format(self.si,self.shift,
                                                         self.minsi, self.maxsi)

    # ------------------------------------------------------------------------------
    #                          OTHER
    # ------------------------------------------------------------------------------
    def signed(self):
      ''' return integer with the signed value of the stored integer 

      The fixbv.signed() function will classify the value of the stored
      insteger either as signed or unsigned. If the value is classified
      as signed it will be returned unchanged as integer value. If the
      value is considered unsigned, the bits as specified by _nrbits
      will be considered as 2's complement number and returned. This
      feature will allow to create slices and have the sliced bits be
      considered a 2's complement number.

      The classification is based on the following possible combinations
      of the min and max value.
          
        ----+----+----+----+----+----+----+----
           -3   -2   -1    0    1    2    3
      1                   min  max
      2                        min  max
      3              min       max
      4              min            max
      5         min            max
      6         min       max
      7         min  max
      8   neither min nor max is set
      9   only max is set
      10  only min is set

      From the above cases, # 1 and 2 are considered unsigned and the
      signed() function will convert the value to a signed number.
      Decision about the sign will be done based on the msb. The msb is
      based on the _nrbits value.
      
      So the test will be if min >= 0 and _nrbits > 0. Then the instance
      is considered unsigned and the value is returned as 2's complement
      number.
      '''

      # value is considered unsigned
      if self.min is not None and self.min >= 0 and self.nrbits > 0:

        # get 2's complement value of bits
        msb = self.nrbits-1

        sign = ((self.si >> msb) & 0x1) > 0
        
        # mask off the bits msb-1:lsb, they are always positive
        mask = (1<<msb) - 1
        retVal = self.si & mask
        # if sign bit is set, subtract the value of the sign bit
        if sign:
          retVal -= 1<<msb

      else: # value is returned just as is
        retVal = self.si

      return retVal

#-- end of class 'fixbv' ------------------------------------------------------------------------

# In some situations it is convenient to initialize the fixbv with a real-world-value. Although fixbv could make a
# distinction between 10.0 and 10, it should not draw conclusions of what type of initialization is required
# based on the type of the initialization value (float or int). Therefore it chosen to create a special class,
# where only the init-function is different.
#class fixbvrw(fixbv):
#    def __init__(self, val = 0.0, fractionlength = 0, min = None, max = None):
#        # val, min and max are interpreted as real-world-values.
#        # fractionlength indicates the number of fractional bits used and therefore is indicates the resolution of
#        # the fixed-point-value.
#        assert (min is None and max is None) or (min is not None and max is not None), 'Expected either min AND max equal to None or min and max not equal to None'
#        self.si = int(floor(val * 2**fractionlength + 0.5)) # In python 2, 'int' rounds towards 0
#        self._shift = -fractionlength
#        if min is not None:
#            self.minsi = int(floor(min * 2 ** fractionlength + 0.5))
#        if max is not None:
#            assert min < max, 'Exptected min < max, but got min=%d and max=%d instead' % (min, max)
#            self.maxsi = int(floor(max * 2 ** fractionlength + 0.5))
#        self._handleBounds()
#
if __name__ == "__main__":
    a = fixbv(10, 2, min = None, max = None)
    b = fixbv(10.5, -2, min=None, max=None)
    c = fixbv(42.4 / 4, 2, min=None, max=None)
    d = fixbv(42.5 / 4, 2, min=None, max=None)
    e = fixbv(42.6 / 4, 2, min=None, max=None)

    f = fixbv(a)

    print(a)
    print(b)
    print(c)
    print(d)
    print(e)

    print(a == f)


    # import random
    # for k in xrange(10):
    #     val = random.randint(-2**31, 2**31)
    #     N = random.randint(-31, 31)
    #     a = fixbv(val, N)
    #     print '%s / %s = %.15f' % (a, a, a/a)
    #     assert (a / a == 1)

    a = fixbv(11, -3)
    b = fixbv(1, -2)

    (c, d) = a.align(b)

    print(c)
    print(d)

    # c = a % b
    # print c
    # print float(a)
    # print float(b)
    # print float(a) % float(b)
