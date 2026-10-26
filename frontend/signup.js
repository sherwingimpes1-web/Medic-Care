/* MEDIC CARE – Sign up page */

const $ = (id) => document.getElementById(id);
const t = (k, v) => (window.I18N ? I18N.t(k, v) : k);

const fields = {
    name: ["fullName", "nameMsg"],
    id: ["emailOrPhone", "idMsg"],
    pw: ["password", "pwMsg"],
    cf: ["confirmPassword", "cfMsg"]
};

/* ---------- Validation messages ---------- */

function setErr(key, msg) {
    const [inputId, msgId] = fields[key];

    $(msgId).textContent = msg || "";
    $(inputId).classList.toggle("invalid", !!msg);
}

function clearAll() {
    Object.keys(fields).forEach((key) => setErr(key, ""));
}

Object.values(fields).forEach(([inputId]) => {
    $(inputId).addEventListener("input", clearAll);
});

/* ---------- Sign up ---------- */

$("signupForm").addEventListener("submit", (e) => {
    e.preventDefault();

    clearAll();

    const name = $("fullName").value.trim();
    const id = $("emailOrPhone").value.trim();
    const pw = $("password").value;
    const cf = $("confirmPassword").value;

    let eName = "";
    let eId = "";
    let ePw = "";
    let eCf = "";

    // Full name validation
    if (!name) {
        eName = "Please enter your full name.";
    } else if (name.length > 200) {
        eName = "Full name must not exceed 200 characters.";
    }

    // Email or phone validation
    if (!Auth.validId(id)) {
        eId = t("sig.err.id");
    }

    // Password validation
    if (pw.length < 😎 {
        ePw = t("sig.err.len");
    } else if (!/[A-Za-z]/.test(pw) || !/\d/.test(pw)) {
        ePw = t("sig.err.mix");
    }

    // Confirm password validation
    if (!cf) {
        eCf = t("sig.err.cf");
    } else if (!ePw && pw !== cf) {
        eCf = t("sig.err.match");
    }

    setErr("name", eName);
    setErr("id", eId);
    setErr("pw", ePw);
    setErr("cf", eCf);

    // Focus the first invalid field
    if (eName || eId || ePw || eCf) {
        const firstInvalid = eName
            ? "fullName"
            : eId
            ? "emailOrPhone"
            : ePw
            ? "password"
            : "confirmPassword";

        $(firstInvalid).focus();
        return;
    }

    // Send the patient's name and credentials to the backend
    const res = Auth.createUser(id, pw, { name: name });

    // Handle registration errors
    if (!res.ok) {
        if (res.error === "exists") {
            setErr("id", t("sig.err.exists"));
        } else if (res.error === "invalid_name") {
            setErr("name", "Please enter a valid full name.");
        } else if (res.error === "invalid_id") {
            setErr("id", t("sig.err.id"));
        } else if (res.error === "weak_password") {
            setErr("pw", t("sig.err.len"));
        } else {
            setErr(
                "id",
                "Unable to create your account. Please try again."
            );
        }

        const errorField = eId || res.error === "invalid_id"
            ? "emailOrPhone"
            : eName || res.error === "invalid_name"
            ? "fullName"
            : "emailOrPhone";

        $(errorField).focus();
        return;
    }

    // Redirect to login after successful registration
    location.href = "index.html?created=1";
});

/* ---------- Language changes ---------- */

window.addEventListener("langchange", clearAll);
