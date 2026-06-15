#ifndef RAW_PROTO_H
#define RAW_PROTO_H

#include <stdint.h>

#define RAW_ETHERTYPE 0x1122
#define RAW_MAGIC "BETH"
#define RAW_VERSION_V2 2
#define RAW_MSG_REQUEST 1
#define RAW_MSG_RESPONSE 2
#define RAW_STATUS_OK 0
#define RAW_PAYLOAD_V2_SIZE 16
#define RAW_ETH_PAYLOAD_PADDED_SIZE 1500
#define RAW_ETH_FRAME_PADDED_SIZE (14 + RAW_ETH_PAYLOAD_PADDED_SIZE)

static inline void raw_write_be16(unsigned char *ptr, uint16_t value)
{
	ptr[0] = (unsigned char)(value >> 8);
	ptr[1] = (unsigned char)value;
}

static inline void raw_write_be32(unsigned char *ptr, uint32_t value)
{
	ptr[0] = (unsigned char)(value >> 24);
	ptr[1] = (unsigned char)(value >> 16);
	ptr[2] = (unsigned char)(value >> 8);
	ptr[3] = (unsigned char)value;
}

static inline uint16_t raw_read_be16(const unsigned char *ptr)
{
	return ((uint16_t)ptr[0] << 8) | ptr[1];
}

static inline uint32_t raw_read_be32(const unsigned char *ptr)
{
	return ((uint32_t)ptr[0] << 24) | ((uint32_t)ptr[1] << 16) |
	       ((uint32_t)ptr[2] << 8) | ptr[3];
}

#endif
