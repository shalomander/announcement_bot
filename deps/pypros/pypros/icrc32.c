#include <stdint.h>
#include <assert.h>

#define SCALE_F (sizeof(unsigned long))

uint32_t icrc32(uint32_t crc, const char* in, int len)
{
    unsigned int iquotient = len / SCALE_F;
    unsigned int iremainder = len % SCALE_F;
    unsigned long *ptmp = (unsigned long *)in;

    while (iquotient--) {
        __asm__ __volatile__( ".byte 0xf2, 0x48, 0xf, 0x38, 0xf1, 0xf1"
                :"=S"(crc)
                :"0"(crc), "c"(*ptmp));
        ptmp++;
    }

    unsigned char *puchar = (unsigned char *)ptmp;
    while (iremainder--) {
        __asm__ __volatile__(
                ".byte 0xf2, 0xf, 0x38, 0xf0, 0xf1"
                :"=S"(crc)
                :"0"(crc), "c"(*puchar)
                );
        puchar++;
    }

    return crc;
}

