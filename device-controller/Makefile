CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra -pedantic -std=c11
GPIOD_CFLAGS ?= $(shell pkg-config --cflags libgpiod 2>/dev/null)
GPIOD_LDLIBS ?= $(shell pkg-config --libs libgpiod 2>/dev/null || echo -lgpiod)

all: controller-once controller-loop

controller-once: controller-once.c raw_client.c raw_client.h raw_proto.h
	$(CC) $(CFLAGS) -o $@ controller-once.c raw_client.c

controller-loop: controller-loop.c raw_client.c raw_client.h raw_proto.h
	$(CC) $(CFLAGS) -o $@ controller-loop.c raw_client.c

controller-gpio-loop: controller-gpio-loop.c raw_client.c raw_client.h raw_proto.h
	$(CC) $(CFLAGS) $(GPIOD_CFLAGS) -o $@ controller-gpio-loop.c raw_client.c $(GPIOD_LDLIBS)

clean:
	rm -f controller-once controller-loop controller-gpio-loop

.PHONY: all clean
