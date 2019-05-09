# altheadergen
Utility to create struct based .h files from AVR ATDF files

Welcome one and all.

Before you go any further read this thread

This is a utility to create device header files for AVRs. Why, you may ask, rther when <avr/io.h> (GCC) and alternatives already exist? The thing is that most device headers (until you reach Xmega) are done in terms of #defines. In fact they are typically things like:

    #define PORTB *(uint8_t *)0x38
 

or something along those lines. So by the time this reaches a debugger the code just uses anonymous accesses to location 0x38 (or I/O 0x18) without any sign of the "PORTB" label.

The idea here is to create a whole new set of header files (by reading Atmel XML) that define this and all other registers/bits in terms of struct members and bitfields so that infomation will form part of the debug image.

So an existing iom16.h may have:

    #define PORTB   _SFR_IO8(0x18)
    #define PB0     0
    #define PB1     1
    #define PB2     2
    #define PB3     3
    #define PB4     4
    #define PB5     5
    #define PB6     6
    #define PB7     7
 

while this generator will create something like:

	union {
		uint8_t reg; // (@ 0x38) Port B Data Register
		struct {
			unsigned int b0:1;
			unsigned int b1:1;
			unsigned int b2:1;
			unsigned int b3:1;
			unsigned int b4:1;
			unsigned int b5:1;
			unsigned int b6:1;
			unsigned int b7:1;
		} bit;
	} _PORTB;
 

for the same thing - which is just one element within a large, composite structure that covers all the SFR registers.

The header defines the entire layout in terms of a typedef struct called:

    typedef struct {
          ...
    } SFRS_t;

and defines a macro to instantiate this at hte correct address for the SFR base:

    #define USE_SFRS() volatile SFRS_t * const pSFR = (SFRS_t *)0x0020
 
So the user code could now use:

    #include "newstyleheader.h"

    USE_SFRS();

    int main(void) {
      pSFR->_PORTB.reg = 0xFF;
      etc.
    }

Though this may be a litte cumbersome. So the auto-generated header also defines some macros to give structure elements like this "easier to handle names". Such as:

    /* ================= (PORTB) Port B Data Register ================ */
    #define portb pSFR->_PORTB.reg
    #define portb_b0 pSFR->_PORTB.bit.b0
    #define portb_b1 pSFR->_PORTB.bit.b1
    #define portb_b2 pSFR->_PORTB.bit.b2
    #define portb_b3 pSFR->_PORTB.bit.b3
    #define portb_b4 pSFR->_PORTB.bit.b4
    #define portb_b5 pSFR->_PORTB.bit.b5
    #define portb_b6 pSFR->_PORTB.bit.b6
    #define portb_b7 pSFR->_PORTB.bit.b7
 

So the code can be simplified as something like:

    #include "newstyleheader.h"

    USE_SFRS();

    #define RED_LED portb_b3

    int main(void) {
      portb = 0xFF;
      RED_LED = 1;
      etc.
    }

To Be Continued...