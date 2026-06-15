CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra -pedantic -std=c11

all: controller-once controller-loop

controller-once: controller-once.c raw_client.c raw_client.h raw_proto.h
	$(CC) $(CFLAGS) -o $@ controller-once.c raw_client.c

controller-loop: controller-loop.c raw_client.c raw_client.h raw_proto.h
	$(CC) $(CFLAGS) -o $@ controller-loop.c raw_client.c

clean:
	rm -f controller-once controller-loop

.PHONY: all clean
