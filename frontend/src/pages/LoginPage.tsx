import { useState, useCallback, useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import axiosInstance, { setCookie } from "../api";
import {
  jwtCookieMaxAgeSeconds,
  scheduleNextRefreshBeforeExpiry,
} from "../authSession/index.ts";
import { useNavigate } from "../RouterUtils";
import {
  FaEye,
  FaEyeSlash,
  FaSignInAlt,
  FaUser,
  FaLock,
  FaCheckCircle,
} from "react-icons/fa";
import logoSrc from "../assets/logo.png";
import { apiUrl, isDebug } from "../../apiConfig";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "../store/hooks";

const LoginPage = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loginError, setLoginError] = useState("");
  const [failedAttempts, setFailedAttempts] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<{
    username?: string;
    password?: string;
  }>({});
  const [touchedFields, setTouchedFields] = useState<{
    username: boolean;
    password: boolean;
  }>({
    username: false,
    password: false,
  });
  const { setUser, setTokens, setLoading } = useAuth();
  const usernameInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const location = useLocation();

  const getRedirectPath = useCallback((): string => {
    const from = (location.state as { from?: { pathname?: string } })?.from;
    const pathname = from?.pathname;
    if (!pathname || pathname === "/app/login") return "/";

    const candidate = pathname.startsWith("/app")
      ? pathname.slice(4) || "/"
      : pathname;

    const isInternal =
      candidate.startsWith("/") &&
      candidate[1] !== "/" &&
      candidate[1] !== "\\" &&
      !candidate.includes(":");
    return isInternal ? candidate : "/";
  }, [location]);

  useEffect(() => {
    usernameInputRef.current?.focus();
  }, []);

  const validateForm = useCallback((): boolean => {
    const errors: { username?: string; password?: string } = {};

    if (!username.trim()) {
      errors.username = "Логин обязателен для заполнения";
    }

    if (!password) {
      errors.password = "Пароль обязателен для заполнения";
    } else if (password.length < 3) {
      errors.password = "Пароль слишком короткий";
    }

    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }, [username, password]);

  const handleSubmit = useCallback(async () => {
    if (isSubmitting) return;

    setTouchedFields({ username: true, password: true });

    if (!validateForm()) {
      return;
    }

    const formattedUsername = username.trim().toLowerCase();
    setIsSubmitting(true);
    setLoginError("");
    setFieldErrors({});

    try {
      const res = await axiosInstance.post(
        "/token/",
        { username: formattedUsername, password },
        { skipAuthInterceptor: true },
      );

      setCookie("access_token", res.data.access, {
        path: "/",
        secure: !isDebug,
        sameSite: isDebug ? "Lax" : "Strict",
        maxAge: jwtCookieMaxAgeSeconds(res.data.access),
      });
      setCookie("refresh_token", res.data.refresh, {
        path: "/",
        secure: !isDebug,
        sameSite: isDebug ? "Lax" : "Strict",
        maxAge: jwtCookieMaxAgeSeconds(res.data.refresh),
      });
      scheduleNextRefreshBeforeExpiry();
      setFailedAttempts(0);

      setTokens({
        access: res.data.access,
        refresh: res.data.refresh,
        accessTokenExpires: res.data.access_token_expires,
        refreshTokenExpires: res.data.refresh_token_expires,
      });

      if (res.data.user) {
        setUser(res.data.user);
      } else {
        setUser({ id: 0, username: formattedUsername, is_banned: false });
      }

      setLoading(false);
      setIsSuccess(true);

      window.dispatchEvent(new Event("userLoggedIn"));

      setTimeout(() => {
        navigate(getRedirectPath());
      }, 800);
    } catch (error: unknown) {
      console.error("Login error:", error);
      let errorMessage =
        "Ошибка входа. Проверьте введённые данные или попробуйте позже.";

      if (error && typeof error === "object" && "response" in error) {
        const axiosError = error as {
          response?: { status?: number; data?: { detail?: string } };
        };
        if (axiosError.response?.status === 401) {
          errorMessage = "Неверный логин или пароль";
        } else if (axiosError.response?.data?.detail) {
          errorMessage = axiosError.response.data.detail;
        }
      }

      setLoginError(errorMessage);
      setFailedAttempts((prev) => prev + 1);
      setTimeout(() => {
        setLoginError("");
      }, 5000);
    } finally {
      setIsSubmitting(false);
    }
  }, [
    username,
    password,
    navigate,
    setUser,
    setTokens,
    setLoading,
    isSubmitting,
    validateForm,
    getRedirectPath,
  ]);

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !isSubmitting) {
      handleSubmit();
    }
  };

  const handleFieldBlur = (field: "username" | "password") => {
    setTouchedFields((prev) => ({ ...prev, [field]: true }));
    if (field === "username" && !username.trim()) {
      setFieldErrors((prev) => ({
        ...prev,
        username: "Логин обязателен для заполнения",
      }));
    } else if (field === "password" && !password) {
      setFieldErrors((prev) => ({
        ...prev,
        password: "Пароль обязателен для заполнения",
      }));
    } else {
      setFieldErrors((prev) => ({ ...prev, [field]: undefined }));
    }
  };

  const fieldState = (field: "username" | "password") =>
    touchedFields[field] && fieldErrors[field] ? "true" : undefined;

  return (
    <div className="login">
      <div className="shell-crest shell-crest-page" aria-hidden />
      <div className="shell-crest login-crest" aria-hidden />
      <motion.form
        className="login-panel"
        initial={{ opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        onSubmit={(e) => {
          e.preventDefault();
          handleSubmit();
        }}
        noValidate
      >
        <div className="login-brand">
          <img src={logoSrc} alt="" />
          <div>
            <h1>Посещаемость</h1>
            <p>КРМУ · вход в систему</p>
          </div>
        </div>

        <div className="ws-field">
          <label htmlFor="login-username">Логин</label>
          <div className="ws-input" data-invalid={fieldState("username")}>
            <FaUser aria-hidden />
            <input
              id="login-username"
              ref={usernameInputRef}
              value={username}
              onChange={(e) => {
                setUsername(e.target.value);
                if (touchedFields.username)
                  setFieldErrors((prev) => ({ ...prev, username: undefined }));
              }}
              onBlur={() => handleFieldBlur("username")}
              placeholder="Логин"
              type="text"
              name="username"
              autoComplete="username"
              disabled={isSubmitting}
              aria-invalid={!!fieldState("username")}
              aria-describedby={fieldState("username") && "username-error"}
            />
          </div>
          <AnimatePresence>
            {fieldState("username") && (
              <motion.p
                id="username-error"
                className="ws-field-error"
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
              >
                {fieldErrors.username}
              </motion.p>
            )}
          </AnimatePresence>
        </div>

        <div className="ws-field">
          <label htmlFor="login-password">Пароль</label>
          <div className="ws-input" data-invalid={fieldState("password")}>
            <FaLock aria-hidden />
            <input
              id="login-password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                if (touchedFields.password)
                  setFieldErrors((prev) => ({ ...prev, password: undefined }));
              }}
              onBlur={() => handleFieldBlur("password")}
              onKeyDown={handleKeyPress}
              placeholder="Пароль"
              type={showPassword ? "text" : "password"}
              name="password"
              autoComplete="current-password"
              disabled={isSubmitting}
              aria-invalid={!!fieldState("password")}
              aria-describedby={fieldState("password") && "password-error"}
            />
            <button
              type="button"
              className="ws-input-action"
              onClick={() => setShowPassword(!showPassword)}
              aria-pressed={showPassword}
              disabled={isSubmitting}
              aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
            >
              {showPassword ? (
                <FaEyeSlash aria-hidden />
              ) : (
                <FaEye aria-hidden />
              )}
            </button>
          </div>
          <AnimatePresence>
            {fieldState("password") && (
              <motion.p
                id="password-error"
                className="ws-field-error"
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
              >
                {fieldErrors.password}
              </motion.p>
            )}
          </AnimatePresence>
        </div>

        <button
          type="submit"
          className="ws-btn-primary login-submit"
          disabled={isSubmitting || isSuccess}
        >
          {isSuccess ? (
            <FaCheckCircle aria-hidden />
          ) : isSubmitting ? (
            <span className="ws-spinner" aria-hidden />
          ) : (
            <FaSignInAlt aria-hidden />
          )}
          {isSuccess ? "Готово" : isSubmitting ? "Входим…" : "Войти"}
        </button>

        <AnimatePresence>
          {loginError && (
            <motion.p
              role="alert"
              className="login-error"
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 4 }}
            >
              {loginError}
            </motion.p>
          )}
        </AnimatePresence>

        <a
          className="login-link"
          href={`${apiUrl}/password-reset`}
          target="_blank"
          rel="noopener noreferrer"
        >
          {failedAttempts >= 2
            ? "Не получается войти? Сбросить пароль"
            : "Забыли пароль?"}
        </a>
      </motion.form>
      <p className="login-credit">
        © {new Date().getFullYear()} КРМУ · Учёт посещаемости
      </p>
    </div>
  );
};

export default LoginPage;
