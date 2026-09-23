/**
 * fakeEventSource.js - a scriptable stand-in for the browser's EventSource.
 *
 * jsdom has no EventSource, and a real one would need a server. Install with
 * `vi.stubGlobal("EventSource", FakeEventSource)`; each `new EventSource(...)` is recorded in
 * `FakeEventSource.instances`, and a test plays the server's part by calling `.open()`,
 * `.emit(...)` and `.fail(...)` on it.
 */
export class FakeEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;

  static instances = [];

  static reset() {
    FakeEventSource.instances = [];
  }

  static get last() {
    return FakeEventSource.instances[FakeEventSource.instances.length - 1];
  }

  constructor(url, options) {
    this.url = url;
    this.options = options;
    this.readyState = FakeEventSource.CONNECTING;
    this.closed = false;
    this.listeners = {};

    FakeEventSource.instances.push(this);
  }

  addEventListener(type, listener) {
    (this.listeners[type] ||= []).push(listener);
  }

  close() {
    this.readyState = FakeEventSource.CLOSED;
    this.closed = true;
  }

  /** The connection was accepted. */
  open() {
    this.readyState = FakeEventSource.OPEN;
    this.onopen?.();
  }

  /** The server sent an event. A non-string payload is JSON-encoded, as the real server does. */
  emit(type, payload) {
    const data = typeof payload === "string" ? payload : JSON.stringify(payload);
    (this.listeners[type] || []).forEach((listener) => listener({ data }));
  }

  /**
   * The connection failed. `closed: true` is the browser giving up (the server answered 401/5xx);
   * otherwise it is a dropped connection the browser will retry on its own.
   */
  fail({ closed = false } = {}) {
    this.readyState = closed ? FakeEventSource.CLOSED : FakeEventSource.CONNECTING;
    this.onerror?.();
  }
}
