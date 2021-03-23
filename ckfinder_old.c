/*
 * This is TASC, or Tasc, or \->ASC, or what-have-you, by Jonathan
 * T. Higa, version 2.52, from Horn Goodies Disk 7. Modified 2020 by
 * Liam Hays to do nothing but create the ASCII representation (in
 * memory, not on the screen), and then calculate its checksum. My
 * goal with this code is to have something that makes only a
 * checksum, finds the ROM version, and determines the size.
 *
 * This is distributed, in source, with HPex, to aid the user in
 * uploading a file to their calculator correctly. This means I took
 * out everything but some of the useful info, the crc and lowbit
 * macros, bintoasc, and the push- and popbit functions, which are all
 * that bintoasc() needs to run.
 *
 * Within bintoasc(), I removed return values in lieu of a main and
 * reformatted the code (actually, all around) to K&R indentation and
 * to be more readable.
 */

#include <ctype.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// no need for ulong, I changed them all to unsigned long.

// ROMFMT, BYTESFMT, and HALFFMT are now hardcoded

// the rom variable is never used, so I took it out

// reformatted a little by me
#define calc_crc(crc, hex) (crc = (crc >> 4) ^ (((crc ^ hex) & 0xF) * 0x1081))

/* Recalculates the Cyclic Redundancy Check value based on the old CRC
   value crc and a new nibble hex.
   Note:  crc should be an unsigned lvalue initialized to 0. */

// Creates an unsigned long with only the low n bits set.
#define lowbits(n) ((1uL << n) - 1uL)

unsigned long popbitq(unsigned long *buf, unsigned int *bsize, int nbits) {
/* Returns the lowest nbits bits of *buf.
   Removes those bits from *buf and adjusts *bsize appropriately. */

  unsigned long b;
  b = *buf & lowbits(nbits);
  *buf >>= nbits;
  if ((*bsize -= nbits) < 0) {
    fputs("tasc: Bit buffer underflow\n", stderr);
    exit(1);
  }
  return b;
}

// -Wall and -Wpedantic say that signedness of bsize in this and
// popbitq differ, so I made it right.
unsigned long pushbitq(unsigned long *buf, unsigned int *bsize,
                       int nbits, unsigned long bits) {
/* Pushes the low nbits of bits onto the high end of *buf.
   Adjusts *bsize appropriately.
   Returns the bits actually pushed. */
  bits &= lowbits(nbits);
  *buf |= bits << *bsize;
  if ((*bsize += nbits) > sizeof *buf * CHAR_BIT) {
    fputs("tasc: Bit buffer overflow\n", stderr);
    exit(1);
  }
  return bits;
}


void bintoasc(char* input_file) {
  // Translates HP48 binary to ASC format.

  FILE *fbin = fopen(input_file, "r");

  unsigned long buf = 0, crc = 0, skip = 0;
  // this used to be declared as nothing and initialized later
  long nibs = 0;

  unsigned int bsize = 0, c = 0;

  enum { NONE, SIZE, ASCIC, ASCIX, DIR } state = NONE;

  // Liam took out MAXWIDTH, as it was used to print newlines for the
  // \->ASC listing

  char str[7];

  // check input for "HPHP48-" header
  if (fread(str, 1, 7, fbin) != 7 || strncmp(str, "HPHP48-", 7) || (c = getc(fbin)) == EOF) {
    fputs("tasc: bad file format\n", stderr);
    exit(1);
  }

  fprintf(stdout, "%c ", (char)c);

  // no header for ASC here, because we're not saving the ASC data

  // nibs used to be reset to zero here, but there's no reason it
  // can't be declared as zero
  while ((c = getc(fbin)) != EOF) {
    pushbitq(&buf, &bsize, CHAR_BIT, c);

    // parse input HP objects
    if (!skip)
      switch (state) {
      case NONE: if (bsize >= 20) {
	  unsigned long pro = buf & lowbits(20);
	  skip = 5;
	  // Liam reformatted this to use braces in all the blocks
	  if (pro == 0x29e8uL || pro == 0x2a0auL || pro == 0x2a2cuL
	      || pro == 0x2a4euL || pro == 0x2b1euL || pro == 0x2b40uL
	      || pro == 0x2b62uL || pro == 0x2b88uL || pro == 0x2dccuL) {
	    state = SIZE;
	  } else if (pro == 0x2e48uL || pro == 0x2e6duL || pro == 0x2afcuL) {
	    state = ASCIC;
	  } else if (pro == 0x2a96uL) {
	    state = DIR;
	    skip = 8;
	  } else if (pro == 0x2911uL) {
	    skip = 10;
	  } else if (pro == 0x2933uL) {
	    skip = 21;
	  } else if (pro == 0x2955uL) {
	    skip = 26;
	  } else if (pro == 0x2977uL) {
	    skip = 37;
	  } else if (pro == 0x299duL) {
	    skip = 47;
	  } else if (pro == 0x29bfuL) {
	    skip = 7;
	  } else if (pro == 0x2e92uL) {
	    skip = 11;
	  }
	}
	break;
      case SIZE:
	if (bsize >= 20) {
	  state = NONE;
	  skip = buf & lowbits(20);
	}
	break;
      case ASCIC:
	if (bsize >= 8) {
	  state = NONE;
	  skip = 2 + 2 * (buf & lowbits(8));
	}
	break;
      case ASCIX:
	if (bsize >= 8) {
	  state = NONE;
	  skip = 4 + 2 * (buf & lowbits(8));
	}
	break;
      case DIR:
	if (bsize >= 20) {
	  state = ASCIX;
	  skip = buf & lowbits(20);
	}
	break;
      }

    // we don't even write any data out here, but we run all the same
    // functions as usual.
    while (skip && bsize >= 4) {
      c = (int) popbitq(&buf, &bsize, 4);

      calc_crc(crc, c);
      skip--;
      nibs++;
    }
  }

  if (buf) {
    fprintf(stderr, "bin->ASC: Binary parsed incorrectly\n");
    exit(1);
  }

  // print out the CRC
  buf = crc;
  bsize = 16;
  while (bsize) {
    // popbitq affects the variables passed into it, so we have to
    // call it, even though we aren't using its return value.
    popbitq(&buf, &bsize, 4);
  }

  fprintf(stdout, "#%lXh %ld%s\n", crc, nibs / 2, nibs & 1 ? ".5" : "");

  /* In the end, this function will print something that looks like
   * this:
   * R #2CCCh 72077.5
   * Python can process this and get all the information it needs.
   */
}

int main(int argc, char* argv[]) {
  // this check is just for good measure
  if (argc != 2) {
    printf("%s", "Not enough arguments");
    exit(1);
  }
  bintoasc(argv[1]);
}
