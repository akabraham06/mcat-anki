// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! A minimal, stable C ABI over the Anki Rust engine.
//!
//! The iOS companion links this static library and drives the *same* engine as
//! the desktop app. The protocol mirrors the Python bridge: open a backend from
//! an encoded `BackendInit` message, then call `run_service_method` with a
//! service index, method index and a protobuf-encoded request; the reply is the
//! protobuf-encoded response (or an encoded backend error).
//!
//! Memory rules for callers:
//! * Buffers returned in [`AnkiBuffer`] must be released with
//!   [`anki_free_buffer`].
//! * Error strings from [`anki_backend_open`] must be released with
//!   [`anki_free_string`].
//! * The handle from [`anki_backend_open`] must be released with
//!   [`anki_backend_close`].

use std::ffi::c_char;
use std::ffi::CString;
use std::ptr;

use anki::backend::init_backend;
use anki::backend::Backend;

/// Opaque handle to an open backend.
pub struct BackendHandle {
    backend: Backend,
}

/// An owned byte buffer handed to the caller. Free with [`anki_free_buffer`].
#[repr(C)]
pub struct AnkiBuffer {
    data: *mut u8,
    len: usize,
    /// True when `data` holds an encoded backend error rather than a response.
    is_error: bool,
}

impl AnkiBuffer {
    fn empty() -> Self {
        AnkiBuffer {
            data: ptr::null_mut(),
            len: 0,
            is_error: false,
        }
    }

    fn from_vec(mut bytes: Vec<u8>, is_error: bool) -> Self {
        bytes.shrink_to_fit();
        let len = bytes.len();
        let data = bytes.as_mut_ptr();
        std::mem::forget(bytes);
        AnkiBuffer {
            data,
            len,
            is_error,
        }
    }
}

/// Open a backend from an encoded `anki.backend.BackendInit` message.
///
/// Returns null on failure; when `err_out` is non-null it receives a
/// heap-allocated C string describing the error (free with
/// [`anki_free_string`]).
///
/// # Safety
/// `init_ptr` must point to `init_len` valid bytes.
#[no_mangle]
pub unsafe extern "C" fn anki_backend_open(
    init_ptr: *const u8,
    init_len: usize,
    err_out: *mut *mut c_char,
) -> *mut BackendHandle {
    if init_ptr.is_null() {
        return ptr::null_mut();
    }
    let init = std::slice::from_raw_parts(init_ptr, init_len);
    match init_backend(init) {
        Ok(backend) => Box::into_raw(Box::new(BackendHandle { backend })),
        Err(e) => {
            if !err_out.is_null() {
                let msg = CString::new(e).unwrap_or_else(|_| CString::new("error").unwrap());
                *err_out = msg.into_raw();
            }
            ptr::null_mut()
        }
    }
}

/// Run a backend service method. `input` is the protobuf-encoded request.
///
/// # Safety
/// `handle` must be a live handle from [`anki_backend_open`]; `input_ptr` must
/// point to `input_len` valid bytes.
#[no_mangle]
pub unsafe extern "C" fn anki_backend_command(
    handle: *mut BackendHandle,
    service: u32,
    method: u32,
    input_ptr: *const u8,
    input_len: usize,
) -> AnkiBuffer {
    if handle.is_null() {
        return AnkiBuffer::empty();
    }
    let handle = &*handle;
    let input = if input_ptr.is_null() {
        &[][..]
    } else {
        std::slice::from_raw_parts(input_ptr, input_len)
    };
    match handle.backend.run_service_method(service, method, input) {
        Ok(bytes) => AnkiBuffer::from_vec(bytes, false),
        Err(bytes) => AnkiBuffer::from_vec(bytes, true),
    }
}

/// Release a buffer returned by [`anki_backend_command`].
///
/// # Safety
/// `buf` must have been produced by this library and not already freed.
#[no_mangle]
pub unsafe extern "C" fn anki_free_buffer(buf: AnkiBuffer) {
    if !buf.data.is_null() && buf.len > 0 {
        drop(Vec::from_raw_parts(buf.data, buf.len, buf.len));
    }
}

/// Release a string returned via `err_out` of [`anki_backend_open`].
///
/// # Safety
/// `s` must have been produced by this library and not already freed.
#[no_mangle]
pub unsafe extern "C" fn anki_free_string(s: *mut c_char) {
    if !s.is_null() {
        drop(CString::from_raw(s));
    }
}

/// Close a backend handle.
///
/// # Safety
/// `handle` must have been produced by [`anki_backend_open`] and not already
/// closed.
#[no_mangle]
pub unsafe extern "C" fn anki_backend_close(handle: *mut BackendHandle) {
    if !handle.is_null() {
        drop(Box::from_raw(handle));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // Build an empty BackendInit (all fields default) so the FFI open path can
    // be exercised on the host without any collection.
    fn empty_init() -> Vec<u8> {
        // An empty message is valid protobuf; init_backend fills defaults.
        vec![]
    }

    #[test]
    fn open_and_close_roundtrip() {
        let init = empty_init();
        let mut err: *mut c_char = ptr::null_mut();
        let handle = unsafe { anki_backend_open(init.as_ptr(), init.len(), &mut err as *mut _) };
        assert!(!handle.is_null(), "backend should open from empty init");
        unsafe { anki_backend_close(handle) };
    }

    /// Proves the engine can perform an HTTPS request on this crate's exact
    /// feature set (`anki/rustls` -> `reqwest/rustls-tls`), which is what the
    /// iOS static library is compiled with. With dummy credentials AnkiWeb
    /// rejects the login at the HTTP layer; the point is that we reach that
    /// layer at all. A missing TLS backend instead fails at dispatch with the
    /// url-less "error sending request for url ()" reported on the device.
    ///
    /// Network-gated: run explicitly with
    ///   `cargo test -p anki-ffi -- --ignored host_key_reaches_ankiweb`
    #[test]
    #[ignore = "hits the network; run explicitly to verify the iOS TLS/HTTP stack"]
    fn host_key_reaches_ankiweb_over_https() {
        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap();
        // Same construction as the backend's web_client(): http1-only, default
        // (rustls) TLS backend selected via feature unification.
        let client = reqwest::Client::builder().http1_only().build().unwrap();
        let result = rt.block_on(anki::sync::login::sync_login(
            "ankiffi-network-probe@example.com",
            "not-a-real-password",
            None,
            client,
        ));
        let err = match result {
            Ok(_) => panic!("dummy credentials must not authenticate"),
            Err(e) => e,
        };
        let msg = format!("{err:?}");
        assert!(
            !msg.contains("error sending request for url ()"),
            "request failed before reaching the server (missing TLS backend?): {msg}"
        );
        // Sanity: it should look like an HTTP/auth-level rejection, proving the
        // TLS handshake + request round-trip succeeded.
        println!("host_key error (expected auth/HTTP-level): {msg}");
    }
}
