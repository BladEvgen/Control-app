import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { Link } from "../RouterUtils";
import { AnimatePresence, motion } from "framer-motion";
import {
  FaArrowLeft,
  FaCheck,
  FaCheckCircle,
  FaEnvelopeOpenText,
  FaEye,
  FaEyeSlash,
  FaKey,
  FaLock,
  FaPaperPlane,
  FaUser,
} from "react-icons/fa";
import axiosInstance from "../api";
import logoSrc from "../assets/logo.png";

const RULES: [string, RegExp][] = [
  ["8+ символов", /^.{8,}$/],
  ["Заглавная A–Z", /[A-Z]/],
  ["Строчная a–z", /[a-z]/],
  ["Цифра", /[0-9]/],
  ["Символ #?!@$%^&*-", /[#?!@$%^&*-]/],
];
const RESEND_SECONDS = 5 * 60;

const STEPS = ["Логин или почта", "Ссылка из письма", "Новый пароль"];

const errorText = (error: unknown, fallback: string): string => {
  const data = (
    error as { response?: { data?: { error?: string; detail?: string } } }
  ).response?.data;
  return data?.error ?? data?.detail ?? fallback;
};

const fade = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
  transition: { duration: 0.25, ease: [0.22, 1, 0.36, 1] as const },
};

function RequestForm({ onSent }: { onSent: () => void }) {
  const [identifier, setIdentifier] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!identifier.trim()) {
      setError("Введите логин или почту.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await axiosInstance.post(
        "/password-reset/",
        { identifier: identifier.trim() },
        { skipAuthInterceptor: true },
      );
      onSent();
    } catch (err) {
      setError(
        errorText(err, "Не удалось отправить запрос. Попробуйте позже."),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <motion.form
      key="request"
      className="auth-form"
      onSubmit={submit}
      noValidate
      {...fade}
    >
      <h2>Восстановление доступа</h2>
      <p className="auth-lead">
        Пришлём на почту ссылку для нового пароля. Она действует один час.
      </p>
      <div className="ws-field">
        <label htmlFor="reset-identifier">Логин или почта</label>
        <div className="ws-input" data-invalid={error ? "true" : undefined}>
          <FaUser aria-hidden />
          <input
            id="reset-identifier"
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            autoComplete="username"
            autoFocus
            disabled={busy}
            aria-invalid={!!error}
            aria-describedby={error ? "reset-error" : undefined}
          />
        </div>
        {error && (
          <p id="reset-error" className="ws-field-error" role="alert">
            {error}
          </p>
        )}
      </div>
      <button
        type="submit"
        className="ws-btn-primary login-submit"
        disabled={busy}
      >
        {busy ? (
          <span className="ws-spinner" aria-hidden />
        ) : (
          <FaPaperPlane aria-hidden />
        )}
        {busy ? "Отправляем…" : "Отправить ссылку"}
      </button>
    </motion.form>
  );
}

function SentNotice({ onRetry }: { onRetry: () => void }) {
  const [left, setLeft] = useState(RESEND_SECONDS);
  useEffect(() => {
    const id = window.setInterval(
      () => setLeft((s) => Math.max(0, s - 1)),
      1000,
    );
    return () => window.clearInterval(id);
  }, []);
  const mm = Math.floor(left / 60);
  const ss = String(left % 60).padStart(2, "0");

  return (
    <motion.div key="sent" className="auth-form auth-result" {...fade}>
      <span className="auth-result-icon">
        <FaEnvelopeOpenText aria-hidden />
      </span>
      <h2>Проверьте почту</h2>
      <p className="auth-lead" role="status">
        Если такой пользователь есть, письмо со ссылкой уже в пути. Загляните и
        в «Спам».
      </p>
      <button
        type="button"
        className="ws-btn-ghost auth-wide"
        onClick={onRetry}
        disabled={left > 0}
      >
        {left > 0 ? `Повторно через ${mm}:${ss}` : "Отправить ещё раз"}
      </button>
    </motion.div>
  );
}

function NewPasswordForm({ token }: { token: string }) {
  const [state, setState] = useState<"checking" | "ready" | "invalid" | "done">(
    "checking",
  );
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    axiosInstance
      .get<{ username: string }>(
        `/password-reset/${encodeURIComponent(token)}/`,
        {
          skipAuthInterceptor: true,
        },
      )
      .then((r) => {
        if (!alive) return;
        setUsername(r.data.username);
        setState("ready");
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setError(errorText(err, "Ссылка недействительна или устарела."));
        setState("invalid");
      });
    return () => {
      alive = false;
    };
  }, [token]);

  const passed = RULES.filter(([, re]) => re.test(password)).length;
  const valid = passed === RULES.length;
  const mismatch = confirm.length > 0 && confirm !== password;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!valid || mismatch || !confirm) return;
    setBusy(true);
    setError("");
    try {
      await axiosInstance.post(
        `/password-reset/${encodeURIComponent(token)}/`,
        { password },
        { skipAuthInterceptor: true },
      );
      setState("done");
    } catch (err) {
      setError(errorText(err, "Не удалось сохранить пароль."));
      if ((err as { response?: { status?: number } }).response?.status === 410)
        setState("invalid");
    } finally {
      setBusy(false);
    }
  };

  if (state === "checking")
    return (
      <motion.div key="checking" className="auth-form auth-result" {...fade}>
        <span className="ws-spinner" aria-hidden />
        <p className="auth-lead" role="status">
          Проверяем ссылку…
        </p>
      </motion.div>
    );

  if (state === "invalid")
    return (
      <motion.div key="invalid" className="auth-form auth-result" {...fade}>
        <span className="auth-result-icon" data-tone="bad">
          <FaKey aria-hidden />
        </span>
        <h2>Ссылка не работает</h2>
        <p className="auth-lead" role="alert">
          {error}
        </p>
        <Link className="ws-btn-primary login-submit" to="/password-reset">
          Запросить новую ссылку
        </Link>
      </motion.div>
    );

  if (state === "done")
    return (
      <motion.div key="done" className="auth-form auth-result" {...fade}>
        <span className="auth-result-icon" data-tone="good">
          <FaCheckCircle aria-hidden />
        </span>
        <h2>Пароль изменён</h2>
        <p className="auth-lead" role="status">
          Теперь войдите с новым паролем.
        </p>
        <Link className="ws-btn-primary login-submit" to="/login">
          Войти
        </Link>
      </motion.div>
    );

  return (
    <motion.form
      key="new"
      className="auth-form"
      onSubmit={submit}
      noValidate
      {...fade}
    >
      <h2>Новый пароль</h2>
      <p className="auth-lead">
        Для пользователя <strong>{username}</strong>
      </p>
      <input
        type="text"
        hidden
        readOnly
        autoComplete="username"
        value={username}
      />

      <div className="ws-field">
        <label htmlFor="reset-password">Пароль</label>
        <div className="ws-input">
          <FaLock aria-hidden />
          <input
            id="reset-password"
            type={show ? "text" : "password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            autoFocus
            disabled={busy}
            aria-describedby="reset-rules"
          />
          <button
            type="button"
            className="ws-input-action"
            onClick={() => setShow((v) => !v)}
            aria-pressed={show}
            aria-label={show ? "Скрыть пароль" : "Показать пароль"}
          >
            {show ? <FaEyeSlash aria-hidden /> : <FaEye aria-hidden />}
          </button>
        </div>
        <div
          className="auth-meter"
          data-level={password ? Math.min(4, passed - 1) : undefined}
          aria-hidden
        >
          {RULES.slice(1).map(([label]) => (
            <span key={label} />
          ))}
        </div>
        <ul id="reset-rules" className="auth-rules">
          {RULES.map(([label, re]) => (
            <li key={label} data-ok={re.test(password) || undefined}>
              <FaCheck aria-hidden />
              {label}
            </li>
          ))}
        </ul>
      </div>

      <div className="ws-field">
        <label htmlFor="reset-confirm">Повторите пароль</label>
        <div className="ws-input" data-invalid={mismatch ? "true" : undefined}>
          <FaLock aria-hidden />
          <input
            id="reset-confirm"
            type={show ? "text" : "password"}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
            disabled={busy || !valid}
            aria-invalid={mismatch}
            aria-describedby={mismatch ? "reset-mismatch" : undefined}
          />
        </div>
        {mismatch && (
          <p id="reset-mismatch" className="ws-field-error">
            Пароли не совпадают
          </p>
        )}
      </div>

      {error && (
        <p className="login-error" role="alert">
          {error}
        </p>
      )}

      <button
        type="submit"
        className="ws-btn-primary login-submit"
        disabled={busy || !valid || !confirm || mismatch}
      >
        {busy ? (
          <span className="ws-spinner" aria-hidden />
        ) : (
          <FaCheck aria-hidden />
        )}
        {busy ? "Сохраняем…" : "Сохранить пароль"}
      </button>
    </motion.form>
  );
}

const PasswordResetPage = () => {
  const { token } = useParams<{ token?: string }>();
  const [sent, setSent] = useState(false);
  const step = token ? 2 : sent ? 1 : 0;

  return (
    <div className="login">
      <div className="shell-crest shell-crest-page" aria-hidden />
      <div className="shell-crest login-crest" aria-hidden />
      <motion.div
        className="auth-split"
        initial={{ opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      >
        <aside className="auth-aside">
          <div className="login-brand">
            <img src={logoSrc} alt="" />
            <div>
              <h1>Посещаемость</h1>
              <p>КРМУ · сброс пароля</p>
            </div>
          </div>
          <ol className="auth-steps">
            {STEPS.map((label, i) => (
              <li
                key={label}
                aria-current={i === step ? "step" : undefined}
                data-done={i < step || undefined}
              >
                <span>{i < step ? <FaCheck aria-hidden /> : i + 1}</span>
                {label}
              </li>
            ))}
          </ol>
          <Link className="login-link auth-back" to="/login">
            <FaArrowLeft aria-hidden />
            Вернуться ко входу
          </Link>
        </aside>

        <div className="auth-main">
          <AnimatePresence mode="wait" initial={false}>
            {token ? (
              <NewPasswordForm key="token" token={token} />
            ) : sent ? (
              <SentNotice key="sent" onRetry={() => setSent(false)} />
            ) : (
              <RequestForm key="request" onSent={() => setSent(true)} />
            )}
          </AnimatePresence>
        </div>
      </motion.div>
      <p className="login-credit">
        © {new Date().getFullYear()} КРМУ · Учёт посещаемости
      </p>
    </div>
  );
};

export default PasswordResetPage;
