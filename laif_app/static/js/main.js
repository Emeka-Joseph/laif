/* LAIF Community — interface behaviour
   Everything here is progressive enhancement: with JS disabled the page
   still renders complete and readable. */

document.addEventListener("DOMContentLoaded", () => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---- Sticky nav state ---- */
  const nav = document.querySelector(".nav");
  if (nav) {
    const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  /* ---- Mobile menu ---- */
  const menu = document.querySelector(".menu");
  const links = document.querySelector(".nav-links");
  if (menu && links) {
    menu.setAttribute("aria-label", "Toggle navigation");
    menu.setAttribute("aria-expanded", "false");
    const setOpen = (open) => {
      links.classList.toggle("mobile-open", open);
      menu.textContent = open ? "✕" : "☰";
      menu.setAttribute("aria-expanded", String(open));
    };
    menu.addEventListener("click", () => setOpen(!links.classList.contains("mobile-open")));
    links.querySelectorAll("a").forEach((a) => a.addEventListener("click", () => setOpen(false)));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") setOpen(false);
    });
  }

  /* ---- Gallery crossfade ---- */
  const slides = [...document.querySelectorAll(".slide")];
  const dots = [...document.querySelectorAll(".dot")];
  if (slides.length > 1) {
    let index = 0;
    let timer;

    const show = (next) => {
      slides[index].classList.remove("active");
      if (dots[index]) dots[index].classList.remove("active");
      index = (next + slides.length) % slides.length;
      slides[index].classList.add("active");
      if (dots[index]) dots[index].classList.add("active");
    };

    const start = () => {
      if (reduceMotion) return;
      stop();
      timer = setInterval(() => show(index + 1), 5200);
    };
    const stop = () => clearInterval(timer);

    dots.forEach((dot, i) => {
      dot.style.cursor = "pointer";
      dot.setAttribute("role", "button");
      dot.setAttribute("aria-label", `Show photo ${i + 1}`);
      dot.addEventListener("click", () => {
        show(i);
        start();
      });
    });

    const slider = document.querySelector(".slider");
    if (slider) {
      slider.addEventListener("mouseenter", stop);
      slider.addEventListener("mouseleave", start);
    }
    start();
  }

  /* ---- Scroll reveal ----
     Classes are added by JS so that content is never hidden when JS or
     IntersectionObserver is unavailable. */
  if (!reduceMotion && "IntersectionObserver" in window) {
    const targets = document.querySelectorAll(
      ".section-head, .card, .post-card, .photo-stack, .slider, .split > div, .hero-strip .cell, .live-box, .form-wrap, .table, .notice"
    );
    if (targets.length) {
      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (!entry.isIntersecting) return;
            entry.target.classList.add("in");
            observer.unobserve(entry.target);
          });
        },
        { rootMargin: "0px 0px -8% 0px", threshold: 0.06 }
      );

      targets.forEach((el, i) => {
        el.classList.add("reveal");
        // Stagger siblings slightly for a softer cascade.
        const delay = Math.min(i % 4, 3) * 70;
        if (delay) el.style.transitionDelay = `${delay}ms`;
        observer.observe(el);
      });
    }
  }

  /* ---- Profile picture preview ----
     Shows the chosen file straight away so the member can see what they
     picked before committing to the passcode step. */
  document.querySelectorAll('input[type="file"][data-preview]').forEach((input) => {
    const target = document.getElementById(input.dataset.preview);
    if (!target) return;
    input.addEventListener("change", () => {
      const file = input.files && input.files[0];
      if (!file || !file.type.startsWith("image/")) return;
      target.src = URL.createObjectURL(file);
      target.hidden = false;
      const initials = document.getElementById("avatar-initials");
      if (initials) initials.hidden = true;
    });
  });

  /* ---- Repeatable field rows ----
     A piece of work can point at several websites or social media handles,
     so the link row clones itself on demand. The button is hidden in the
     markup and revealed here: with JS off the single row still submits. */
  document.querySelectorAll("[data-repeat]").forEach((group) => {
    const add = group.querySelector("[data-repeat-add]");
    const first = group.querySelector(".repeat-row");
    if (!add || !first) return;

    const limit = parseInt(group.dataset.repeat, 10) || 1;
    if (limit < 2) return;
    add.hidden = false;

    add.addEventListener("click", () => {
      const rows = group.querySelectorAll(".repeat-row");
      if (rows.length >= limit) return;
      const row = first.cloneNode(true);
      row.querySelectorAll("input").forEach((input) => {
        input.value = "";
        input.removeAttribute("required");
      });
      rows[rows.length - 1].after(row);
      if (rows.length + 1 >= limit) add.hidden = true;
      const focusTarget = row.querySelector("input");
      if (focusTarget) focusTarget.focus();
    });
  });

  /* ---- Portfolio lightbox ----
     Any [data-lightbox] grid becomes browsable: click a tile to open it
     full size, arrow keys or the chevrons to move, Escape or a click on the
     backdrop to close again. Built on demand so pages without a gallery
     carry no extra markup. */
  const galleries = [...document.querySelectorAll("[data-lightbox]")];
  if (galleries.length) {
    const tiles = [];
    galleries.forEach((gallery) => {
      gallery.querySelectorAll(".tile-open").forEach((button) => tiles.push(button));
    });

    if (tiles.length) {
      const box = document.createElement("div");
      box.className = "lightbox";
      box.setAttribute("role", "dialog");
      box.setAttribute("aria-modal", "true");
      box.setAttribute("aria-label", "Portfolio viewer");
      box.innerHTML =
        '<div class="lightbox-stage">' +
        '<button class="lightbox-close" type="button" aria-label="Close">&times;</button>' +
        '<button class="lightbox-prev" type="button" aria-label="Previous">&#8249;</button>' +
        '<button class="lightbox-next" type="button" aria-label="Next">&#8250;</button>' +
        '<div class="lightbox-media"></div>' +
        '<div class="lightbox-copy"></div>' +
        '<div class="lightbox-count"></div>' +
        "</div>";
      document.body.appendChild(box);

      const media = box.querySelector(".lightbox-media");
      const copy = box.querySelector(".lightbox-copy");
      const count = box.querySelector(".lightbox-count");
      const prevBtn = box.querySelector(".lightbox-prev");
      const nextBtn = box.querySelector(".lightbox-next");
      const single = tiles.length < 2;
      prevBtn.hidden = single;
      nextBtn.hidden = single;

      let index = 0;
      let opener = null;

      const render = (i) => {
        index = (i + tiles.length) % tiles.length;
        const tile = tiles[index];
        const { kind, src, title, caption } = tile.dataset;

        // Replacing the node stops a video that was already playing.
        media.innerHTML = "";
        if (kind === "video") {
          const video = document.createElement("video");
          video.src = src;
          video.controls = true;
          video.autoplay = true;
          video.playsInline = true;
          media.appendChild(video);
        } else {
          const img = document.createElement("img");
          img.src = src;
          img.alt = title || "Portfolio item";
          // Clicking the enlarged photo shrinks it back. Videos are left
          // alone so a click reaches their own play/pause controls.
          img.addEventListener("click", () => close());
          media.appendChild(img);
        }

        copy.innerHTML = "";
        if (title) {
          const strong = document.createElement("strong");
          strong.textContent = title;
          copy.appendChild(strong);
        }
        if (caption) {
          const span = document.createElement("span");
          span.textContent = caption;
          copy.appendChild(span);
        }
        count.textContent = single ? "" : `${index + 1} / ${tiles.length}`;
      };

      const open = (i, source) => {
        opener = source || null;
        render(i);
        box.classList.add("open");
        document.body.classList.add("lightbox-open");
        box.querySelector(".lightbox-close").focus();
      };

      const close = () => {
        box.classList.remove("open");
        document.body.classList.remove("lightbox-open");
        media.innerHTML = "";
        if (opener) opener.focus();
      };

      tiles.forEach((tile, i) => tile.addEventListener("click", () => open(i, tile)));
      box.querySelector(".lightbox-close").addEventListener("click", close);
      prevBtn.addEventListener("click", () => render(index - 1));
      nextBtn.addEventListener("click", () => render(index + 1));

      // A click on the backdrop closes; one on the artwork itself does not.
      box.addEventListener("click", (e) => {
        if (e.target === box) close();
      });

      document.addEventListener("keydown", (e) => {
        if (!box.classList.contains("open")) return;
        if (e.key === "Escape") close();
        if (single) return;
        if (e.key === "ArrowLeft") render(index - 1);
        if (e.key === "ArrowRight") render(index + 1);
      });
    }
  }
});
