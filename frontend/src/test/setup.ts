import "@testing-library/jest-dom/vitest";

class TestResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver =
  TestResizeObserver as unknown as typeof ResizeObserver;

Object.defineProperties(HTMLDialogElement.prototype, {
  showModal: {
    value() {
      this.setAttribute("open", "");
    },
  },
  close: {
    value() {
      this.removeAttribute("open");
    },
  },
});

HTMLElement.prototype.scrollTo = vi.fn();

afterEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
