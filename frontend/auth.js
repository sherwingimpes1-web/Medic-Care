/* MEDIC CARE – Shared accounts, login session and sidebar.
   Authentication and patient data are managed by backend/app.py.
   Account information is stored in Supabase through the Python backend.

   Page rules:
   data-requires-login -> redirect guests to index.html
   data-guest-only     -> redirect signed-in users to homepage.html
*/

(function () {
    "use strict";

    const LOGIN = "index.html";
    const HOME = "homepage.html";
    const API = "/api";

    /* ---------- Server calls ---------- */

  
     function call(method, path, body) {
    try {
      const xhr = new XMLHttpRequest();
      xhr.open(method, API + path, false);
      xhr.setRequestHeader("Content-Type", "application/json");
      xhr.send(body === undefined ? null : JSON.stringify(body));
      
      let data = {};
      try { data = JSON.parse(xhr.responseText || "{}"); } catch (e) {}

      // Log the server error details for easier debugging
      if (xhr.status >= 500) {
        console.error(`Server Error (${xhr.status}):`, data.error || xhr.responseText);
      }

      return { status: xhr.status, data };
    } catch (e) {
      return { status: 0, data: { ok: false, error: "network" } };
    }
  }


    /* ---------- Cache of signed-in account ---------- */

    let cache = null;

    function refresh() {
        const r = call("GET", "/me");

        cache =
            r.status === 200 && r.data.user
                ? r.data.user
                : null;

        return cache;
    }

    refresh();

    /* ---------- Email and phone ---------- */

    function normalize(raw) {
        let s = String(raw || "").trim();

        if (s.includes("@")) {
            return s.toLowerCase();
        }

        s = s.replace(/[\s\-().]/g, "");

        if (/^\+63\d{10}$/.test(s)) {
            s = "0" + s.slice(3);
        } else if (/^63\d{10}$/.test(s)) {
            s = "0" + s.slice(2);
        }

        return s;
    }

    const isEmail = (v) =>
        /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v);

    const isPhone = (v) =>
        /^\+?\d{7,15}$/.test(v);

    const validId = (raw) => {
        const n = normalize(raw);
        return isEmail(n) || isPhone(n);
    };

    /* ---------- Default profile ---------- */

    function nameFromId(n) {
        if (!isEmail(n)) {
            return "Patient";
        }

        const words = n
            .split("@")[0]
            .split(/[._\-+0-9]+/)
            .filter(Boolean);

        return (
            words
                .map((w) => w[0].toUpperCase() + w.slice(1))
                .join(" ") || "Patient"
        );
    }

    function defaultProfile(n) {
        return {
            name: nameFromId(n),
            email: isEmail(n) ? n : "",
            phone: isEmail(n) ? "" : n,
            code: "+63",
            photo: ""
        };
    }

    /* ---------- Accounts ---------- */

    function createUser(raw, pw, profile = {}) {
        const name = String(profile.name || "").trim();

        if (!name || name.length > 200) {
            return {
                ok: false,
                error: "invalid_name"
            };
        }

        const r = call("POST", "/signup", {
            id: raw,
            password: pw,
            profile: {
                name: name
            }
        });

        if (r.data && r.data.ok) {
            return {
                ok: true,
                id: r.data.id
            };
        }

        return {
            ok: false,
            error:
                (r.data && r.data.error) ||
                (r.status === 0 ? "network" : "error")
        };
    }

    function verify(raw, pw) {
        const r = call("POST", "/verify", {
            id: raw,
            password: pw
        });

        if (r.data && r.data.ok) {
            return {
                ok: true,
                id: r.data.id
            };
        }

        return {
            ok: false,
            reason:
                (r.data && r.data.reason) ||
                (r.status === 0 ? "network" : "bad")
        };
    }

    function current() {
        return cache ? cache.id : null;
    }

    function login(raw) {
        const r = call("POST", "/login", {
            id: raw
        });

        if (r.data && r.data.ok) {
            refresh();
        }

        return !!(r.data && r.data.ok);
    }

    function logout() {
        call("POST", "/logout");
        cache = null;
    }

    /* ---------- Profile ---------- */

    function profile() {
        return cache
            ? {
                ...defaultProfile(cache.id),
                ...(cache.profile || {})
            }
            : defaultProfile("");
    }

    function saveProfile(patch) {
        if (!cache) {
            return null;
        }

        const r = call("PUT", "/profile", patch);

        if (r.data && r.data.ok) {
            cache.profile = r.data.profile;
            return r.data.profile;
        }

        return null;
    }

    /* ---------- Password ---------- */

    function checkPassword(pw) {
        if (!cache) {
            return false;
        }

        const r = call("POST", "/password/check", {
            password: pw
        });

        return !!(r.data && r.data.ok);
    }

    function setPassword(pw) {
        if (!cache) {
            return false;
        }

        const r = call("PUT", "/password", {
            password: pw
        });

        return !!(r.data && r.data.ok);
    }

    /* ---------- Delete account ---------- */

    function deleteAccount() {
        if (!cache) {
            return;
        }

        const r = call("DELETE", "/account");

        if (r.data && r.data.ok) {
            cache = null;
        }
    }

    /* ---------- Per-account data ---------- */

    function getData(key, fallback) {
        return cache &&
            cache.data &&
            Object.prototype.hasOwnProperty.call(cache.data, key)
                ? cache.data[key]
                : fallback;
    }

    function setData(key, value) {
        if (!cache) {
            return null;
        }

        const r = call(
            "PUT",
            "/data/" + encodeURIComponent(key),
            { value: value }
        );

        if (r.data && r.data.ok) {
            cache.data = cache.data || {};
            cache.data[key] = value;
        }

        return null;
    }

    /* ---------- Appointments ---------- */

    const getAppointments = () =>
        getData("appointments", []).map((a) =>
            a.status === "Pending"
                ? { ...a, status: "Confirmed" }
                : a
        );

    const saveAppointments = (list) =>
        setData("appointments", list);

    const todayISO = () => {
        const d = new Date();

        return (
            d.getFullYear() +
            "-" +
            String(d.getMonth() + 1).padStart(2, "0") +
            "-" +
            String(d.getDate()).padStart(2, "0")
        );
    };

    /* ---------- Public API ---------- */

    const Auth = {
        LOGIN,
        HOME,

        normalize,
        isEmail,
        isPhone,
        validId,

        createUser,
        verify,
        current,
        login,
        logout,

        profile,
        saveProfile,

        checkPassword,
        setPassword,
        deleteAccount,

        getData,
        setData,

        getAppointments,
        saveAppointments,
        todayISO,

        refresh
    };

    window.Auth = Auth;

    /* ---------- Page access rules ---------- */

    function enforcePageRules() {
        const html = document.documentElement;

        if (
            html.hasAttribute("data-requires-login") &&
            !current()
        ) {
            location.replace(LOGIN);
            return;
        }

        if (
            html.hasAttribute("data-guest-only") &&
            current()
        ) {
            location.replace(HOME);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            enforcePageRules
        );
    } else {
        enforcePageRules();
    }

})();
