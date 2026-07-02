// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
//
// C ABI for the Anki Rust engine, consumed by the iOS companion app.

#ifndef ANKIFFI_H
#define ANKIFFI_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct BackendHandle BackendHandle;

// An owned byte buffer. Release with anki_free_buffer.
typedef struct AnkiBuffer {
  uint8_t *data;
  size_t len;
  // True when `data` holds an encoded backend error rather than a response.
  bool is_error;
} AnkiBuffer;

// Open a backend from an encoded anki.backend.BackendInit message.
// Returns NULL on failure; when err_out is non-NULL it receives a
// heap-allocated C string (free with anki_free_string).
BackendHandle *anki_backend_open(const uint8_t *init_ptr, size_t init_len,
                                 char **err_out);

// Run a backend service method. `input` is the protobuf-encoded request; the
// returned buffer is the protobuf-encoded response (or error when is_error).
AnkiBuffer anki_backend_command(BackendHandle *handle, uint32_t service,
                                uint32_t method, const uint8_t *input_ptr,
                                size_t input_len);

void anki_free_buffer(AnkiBuffer buf);
void anki_free_string(char *s);
void anki_backend_close(BackendHandle *handle);

#ifdef __cplusplus
}
#endif

#endif // ANKIFFI_H
