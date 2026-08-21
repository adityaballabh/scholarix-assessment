const KEY = "mergereview.filters";

type Store = Record<string, string>;

function read(): Store {
  try {
    return JSON.parse(window.sessionStorage.getItem(KEY) ?? "{}") as Store;
  } catch {
    return {};
  }
}

// Section is the first path segment, so /reviews/:caseId shares the queue's filters
export function sectionOf(pathname: string): string {
  return pathname.split("/")[1] ?? "";
}

export function rememberSearch(section: string, search: string) {
  try {
    window.sessionStorage.setItem(
      KEY,
      JSON.stringify({ ...read(), [section]: search }),
    );
  } catch {
    // A blocked store just means filters reset between sections
  }
}

export function recallSearch(section: string): string {
  return read()[section] ?? "";
}
