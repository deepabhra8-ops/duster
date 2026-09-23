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

  open() {
    this.readyState = FakeEventSource.OPEN;
    this.onopen?.();
  }

  emit(type, payload) {
    const data = typeof payload === "string" ? payload : JSON.stringify(payload);
    (this.listeners[type] || []).forEach((listener) => listener({ data }));
  }

  fail({ closed = false } = {}) {
    this.readyState = closed ? FakeEventSource.CLOSED : FakeEventSource.CONNECTING;
    this.onerror?.();
  }
}
