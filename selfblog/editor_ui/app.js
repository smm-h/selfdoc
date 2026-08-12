// selfblog editor — the authoring shell.
//
// A tinymoon app: mountShell builds the frame (sidebar, topbar, theme, router),
// one route per registry entry, and each route's view is a post list beside a
// two-pane editor. The editing surface is tinymoon's createEditor — a real
// textarea over a decoration underlay — mounted here with an empty decoration
// set. Spelling and lint decorations arrive later and go in through
// setDecorations()/setGutterMarkers(); nothing about this mount has to change
// to accept them.
//
// The preview pane is an iframe pointed at /preview/<repo>/blog/<slug>/, which
// the server answers with the exact bytes publishing this buffer would produce
// and, for everything the page links to, with the repository's build output. It
// is not a second renderer and not an approximation: it is the publish render
// of an unsaved buffer, which is the whole reason the in-memory render path
// exists.
//
// Nothing here writes to a working tree except the explicit save (Ctrl-S or the
// Save button), which PUTs the buffer. Typing only ever POSTs a preview.

import { el } from "/tinymoon/js/dom.js";
import { mountShell } from "/tinymoon/js/shell.js";
import { createView } from "/tinymoon/js/view.js";
import { loadingBlock, emptyBlock, errorBlock } from "/tinymoon/js/states.js";
import { toast } from "/tinymoon/js/toast.js";
import { createSettings, cycleTheme } from "/tinymoon/js/settings.js";
import { createEditor } from "/tinymoon/js/editor.js";

// How long typing has to pause before a preview is asked for. Long enough that
// a fast typist does not render every keystroke, short enough to feel live.
const PREVIEW_DEBOUNCE_MS = 300;

const settings = createSettings({
  storageKey: "tm-settings",
  defaults: { theme: "system" },
});

// ---------------------------------------------------------------- transport

async function call(path, opts) {
  const res = await fetch(path, opts);
  const text = await res.text();
  let body = null;
  if (text) {
    try { body = JSON.parse(text); } catch (e) { body = null; }
  }
  if (!res.ok) {
    throw new Error((body && body.error) || text || `HTTP ${res.status}`);
  }
  return body;
}

const getJSON = (path) => call(path, { method: "GET" });

const putText = (path, content) => call(path, {
  method: "PUT",
  headers: { "Content-Type": "text/markdown; charset=utf-8" },
  body: content,
});

const postText = (path, content) => call(path, {
  method: "POST",
  headers: { "Content-Type": "text/markdown; charset=utf-8" },
  body: content,
});

// One event stream for the whole app. Views register interest by path; the
// stream itself is opened once and never per view.
const previewListeners = new Set();

function openStream() {
  const source = new EventSource("/events");
  source.addEventListener("preview", (event) => {
    let payload = null;
    try { payload = JSON.parse(event.data); } catch (e) { return; }
    for (const listener of [...previewListeners]) listener(payload);
  });
  source.addEventListener("error", () => {
    // EventSource reconnects on its own; nothing to do but stay quiet about
    // the gap. A hard failure surfaces the next time a request is made.
  });
  return source;
}

// -------------------------------------------------------------------- view

function repoView(repo) {
  let listHost = null;
  let editorHost = null;
  let frame = null;
  let statusLabel = null;
  let saveButton = null;
  let editor = null;
  let posts = [];
  let currentPath = null;
  let pendingPath = null;
  let previewTimer = null;
  let savedText = "";

  function setStatus(text, kind) {
    if (!statusLabel) return;
    statusLabel.textContent = text;
    statusLabel.dataset.kind = kind || "idle";
  }

  function markDirty() {
    const dirty = editor && editor.get() !== savedText;
    if (saveButton) saveButton.disabled = !dirty;
    setStatus(dirty ? "unsaved changes" : "saved", dirty ? "dirty" : "idle");
  }

  function highlightSelection() {
    if (!listHost) return;
    for (const button of listHost.querySelectorAll("[data-post]")) {
      button.setAttribute(
        "aria-current", button.dataset.post === currentPath ? "true" : "false",
      );
    }
  }

  function renderList() {
    listHost.replaceChildren();
    if (!posts.length) {
      listHost.appendChild(emptyBlock({
        title: "No posts",
        note: `${repo.name} has no posts yet.`,
      }));
      return;
    }
    for (const post of posts) {
      const button = el("button", "ed-post");
      button.type = "button";
      button.dataset.post = post.path;
      button.appendChild(el("span", "ed-post-title", post.title));
      const meta = el("span", "ed-post-meta");
      meta.appendChild(el("span", "ed-post-date", post.date));
      if (post.draft) meta.appendChild(el("span", "ed-post-draft", "draft"));
      button.appendChild(meta);
      button.addEventListener("click", () => {
        location.hash = `#/${repo.name}/${post.path}`;
      });
      listHost.appendChild(button);
    }
    highlightSelection();
  }

  async function loadPosts() {
    listHost.replaceChildren(loadingBlock({ note: "Reading posts…" }));
    try {
      const body = await getJSON(`/api/repos/${repo.name}/posts`);
      posts = body.posts;
      renderList();
    } catch (err) {
      posts = [];
      listHost.replaceChildren(errorBlock({
        title: "Cannot list posts",
        note: err.message,
      }));
    }
  }

  function mountEditor(content) {
    if (editor) editor.destroy();
    editorHost.replaceChildren();
    editor = createEditor({
      name: `source-${repo.name}`,
      label: "Post source",
      value: content,
      rows: 24,
      spellcheck: false,
      gutter: true,
      onChange: () => {
        markDirty();
        schedulePreview();
      },
    });
    // The underlay mounts empty. Spelling and lint decorations are the second
    // half of this work and arrive through exactly these two calls.
    editor.setDecorations([]);
    editor.setGutterMarkers([]);
    editorHost.appendChild(editor.el);
  }

  function schedulePreview() {
    if (previewTimer) clearTimeout(previewTimer);
    previewTimer = setTimeout(requestPreview, PREVIEW_DEBOUNCE_MS);
  }

  async function requestPreview() {
    if (!editor || !currentPath) return;
    const path = currentPath;
    try {
      await postText(
        `/api/repos/${repo.name}/preview?path=${encodeURIComponent(path)}`,
        editor.get(),
      );
      // The rendered page arrives on the event stream, not in this response:
      // one channel drives the pane, so a preview triggered anywhere shows up
      // the same way.
    } catch (err) {
      setStatus(err.message, "error");
    }
  }

  async function openPost(path) {
    currentPath = path;
    highlightSelection();
    editorHost.replaceChildren(loadingBlock({ note: "Opening…" }));
    try {
      const body = await getJSON(
        `/api/repos/${repo.name}/document?path=${encodeURIComponent(path)}`,
      );
      savedText = body.content;
      mountEditor(body.content);
      markDirty();
      requestPreview();
    } catch (err) {
      editorHost.replaceChildren(errorBlock({
        title: "Cannot open post",
        note: err.message,
      }));
    }
  }

  async function save() {
    if (!editor || !currentPath) return;
    const content = editor.get();
    try {
      await putText(
        `/api/repos/${repo.name}/document?path=${encodeURIComponent(currentPath)}`,
        content,
      );
      savedText = content;
      markDirty();
      toast(`Saved ${currentPath}`, "ok");
      loadPosts();
    } catch (err) {
      setStatus(err.message, "error");
      toast(err.message, "error");
    }
  }

  function onPreview(payload) {
    if (payload.repo !== repo.name || payload.path !== currentPath) return;
    // Re-point rather than reload: the URL carries the post's published
    // address, which changes when the buffer's slug does.
    frame.src = `${payload.url}?t=${Date.now()}`;
    setStatus(editor && editor.get() !== savedText
      ? "unsaved changes" : "saved",
      editor && editor.get() !== savedText ? "dirty" : "idle");
  }

  function buildUnserved(ctx) {
    ctx.root.appendChild(errorBlock({
      title: "Remote entries are not served yet",
      note: `${repo.name} points at ${repo.repo} @ ${repo.ref}. The registry `
        + `validates remote entries in full, but serving one is not `
        + `implemented.`,
    }));
  }

  function build(ctx) {
    if (!repo.served) {
      buildUnserved(ctx);
      return;
    }

    const wrap = el("div", "ed-wrap");

    const side = el("aside", "ed-side");
    side.appendChild(el("h2", "ed-side-title", "Posts"));
    listHost = el("div", "ed-list");
    side.appendChild(listHost);
    wrap.appendChild(side);

    const main = el("div", "ed-main");

    const bar = el("div", "ed-bar");
    statusLabel = el("span", "ed-status", "no post open");
    saveButton = el("button", "btn ed-save");
    saveButton.type = "button";
    saveButton.textContent = "Save";
    saveButton.disabled = true;
    saveButton.addEventListener("click", save);
    bar.appendChild(statusLabel);
    bar.appendChild(saveButton);
    main.appendChild(bar);

    const panes = el("div", "ed-panes");
    editorHost = el("div", "ed-editor");
    editorHost.appendChild(emptyBlock({
      title: "No post open",
      note: "Pick a post from the list.",
    }));
    frame = el("iframe", "ed-preview");
    frame.setAttribute("title", "Preview");
    panes.appendChild(editorHost);
    panes.appendChild(frame);
    main.appendChild(panes);

    wrap.appendChild(main);
    ctx.root.appendChild(wrap);

    previewListeners.add(onPreview);
    ctx.root.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        save();
      }
    });

    loadPosts();
    if (pendingPath) {
      const path = pendingPath;
      pendingPath = null;
      openPost(path);
    }
  }

  return createView({
    build,
    refresh() {
      if (!repo.served) return;
      if (pendingPath && pendingPath !== currentPath) {
        const path = pendingPath;
        pendingPath = null;
        openPost(path);
      }
    },
    setSub(sub) {
      if (!sub) return;
      pendingPath = sub;
    },
  });
}

// -------------------------------------------------------------------- boot

async function boot() {
  let repos = [];
  try {
    repos = (await getJSON("/api/repos")).repos;
  } catch (err) {
    document.body.appendChild(errorBlock({
      title: "Cannot read the registry",
      note: err.message,
    }));
    return;
  }

  if (!repos.length) {
    document.body.appendChild(emptyBlock({
      title: "The registry is empty",
      note: "Add a [[repo]] block to the registry file and restart.",
    }));
    return;
  }

  const routes = {};
  for (const repo of repos) {
    routes[repo.name] = {
      title: repo.name,
      icon: repo.served ? "docs" : "warn",
      tip: repo.served ? repo.path : `${repo.repo} @ ${repo.ref} (not served)`,
      view: () => repoView(repo),
    };
  }

  mountShell({
    root: document.body,
    brand: {
      name: "selfblog",
      logoHTML: '<div class="wordmark">self<b>blog</b></div>'
        + '<div class="tagline">editor</div>',
    },
    routes,
    defaultRoute: repos[0].name,
    topbarActions: [
      { icon: "moon", tip: "Cycle theme", onClick: () => cycleTheme(settings) },
    ],
  });

  openStream();
}

boot();
