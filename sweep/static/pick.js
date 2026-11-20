/* The front door's picker while more than one résumé fits (the résumé
   setup's batch upload). The native input is still what is sent; this only
   keeps what was chosen across more than one pick or drop — a browser
   replaces an input's files on every pick — lets one be taken out again,
   and says what will be read. Every rule here is also POST /resume's, and
   the server's is the one that holds: this is hearing it before an upload
   rather than after one. Loaded before Alpine, which calls sweepPicker. */
(function () {
  "use strict";

  /* The files to send once `picked` is added to `held`, in the order they
     were chosen, and a sentence for each one left out. Pure, for the test. */
  function merge(held, picked, room, maxBytes, mb) {
    const files = held.slice();
    const bad = [];
    const total = () => files.reduce((n, g) => n + g.size, 0);
    Array.from(picked || []).forEach((f) => {
      if (files.some((g) => g.name === f.name && g.size === f.size &&
                            g.lastModified === f.lastModified)) return;
      if (!/\.pdf$/i.test(f.name)) {
        bad.push(f.name + " is not a PDF. Export your résumé as a PDF and try again.");
      } else if (files.length >= room) {
        bad.push(f.name + " was not added: this upload takes up to " + room +
                 " résumé" + (room === 1 ? "" : "s") + ".");
      } else if (f.size > maxBytes) {
        bad.push(f.name + " is larger than " + mb + " MB. Export a smaller PDF and try again.");
      } else if (total() + f.size > maxBytes) {
        bad.push(f.name + " was not added: together these PDFs would be over " +
                 mb + " MB, the most one upload takes.");
      } else {
        files.push(f);
      }
    });
    return { files: files, bad: bad.join(" ") };
  }

  function size(f) {
    return f.size < 1048576 ? Math.max(1, Math.round(f.size / 1024)) + " KB"
                            : (f.size / 1048576).toFixed(1) + " MB";
  }

  window.sweepPicker = function (room, mb) {
    return {
      sent: false, over: false, files: [], bad: "", room: room,
      take(list) {
        const got = merge(this.files, list || this.$refs.picker.files, room,
                          mb * 1048576, mb);
        this.files = got.files;
        this.bad = got.bad;
        this.sync();
      },
      drop(e) { this.over = false; this.take(e.dataTransfer.files); },
      remove(i) { this.files.splice(i, 1); this.bad = ""; this.sync(); },
      /* The input holds exactly the list on screen. Where a browser cannot
         set an input's files, the list becomes what the input holds
         instead: never a list that is not what will be sent. */
      sync() {
        try {
          const dt = new DataTransfer();
          this.files.forEach((f) => dt.items.add(f));
          this.$refs.picker.files = dt.files;
        } catch (e) {
          this.files = Array.from(this.$refs.picker.files);
        }
      },
      size: size,
    };
  };
  window.sweepPicker.merge = merge;
})();
