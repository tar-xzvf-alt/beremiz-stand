CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra -pedantic -std=c11

all: controller-once

controller-once: controller-once.c raw_proto.h
	$(CC) $(CFLAGS) -o $@ controller-once.c

clean:
	rm -f controller-once

.PHONY: all clean
