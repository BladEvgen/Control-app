import { useState, useCallback, useEffect, useRef } from "react";
import axiosInstance, { setCookie } from "../api";
import { useNavigate } from "../RouterUtils";
import {
  FaEye,
  FaEyeSlash,
  FaSignInAlt,
  FaSpinner,
  FaUser,
  FaLock,
  FaCheckCircle,
} from "react-icons/fa";
import { FaBug } from "react-icons/fa6";
import { apiUrl } from "../../apiConfig";
import { motion, AnimatePresence, Variants } from "framer-motion";
import { useAuth } from "../store/hooks";

const errorVariants = {
  hidden: { opacity: 0, y: -10 },
  visible: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 10 },
};

const pulseVariants: Variants = {
  initial: { scale: 1 },
  animate: {
    scale: [1, 1.05, 1],
    transition: { duration: 1.5, repeat: Infinity, ease: "easeInOut" as const },
  },
};

const containerVariants: Variants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.5,
      staggerChildren: 0.1,
    },
  },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0 },
};

const successVariants: Variants = {
  hidden: { scale: 0, opacity: 0 },
  visible: {
    scale: 1,
    opacity: 1,
    transition: {
      type: "spring",
      stiffness: 200,
      damping: 15,
    },
  },
};

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
        { skipAuthInterceptor: true }
      );

      setCookie("access_token", res.data.access, { path: "/" });
      setCookie("refresh_token", res.data.refresh, { path: "/" });
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
        navigate("/");
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

  return (
    <div className="flex flex-col min-h-screen">
      <div className="flex-grow flex flex-col items-center justify-center p-4">
        <motion.div
          className="card w-full max-w-md p-8 md:p-10 relative"
          variants={containerVariants}
          initial="hidden"
          animate="visible"
        >
          <motion.div variants={itemVariants} className="relative z-10">
            <h2 className="text-2xl md:text-3xl font-bold text-center text-gray-800 dark:text-gray-100 mb-2">
              Добро пожаловать!
            </h2>
            <p className="text-center text-gray-600 dark:text-gray-400 mb-8 text-sm md:text-base">
              Войдите в свою учётную запись
            </p>
          </motion.div>
          <motion.form
            variants={itemVariants}
            onSubmit={(e) => {
              e.preventDefault();
              handleSubmit();
            }}
            className="space-y-5 relative z-10"
          >
            <div className="space-y-5">
              <div>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                    <FaUser
                      className="text-gray-400 dark:text-gray-500"
                      size={18}
                    />
                  </div>
                  <input
                    ref={usernameInputRef}
                    className={`w-full pl-12 pr-4 py-3 text-base border dark:bg-gray-800 rounded-lg focus:outline-none focus:ring-2 transition-all duration-300 text-gray-900 dark:text-gray-100 disabled:opacity-50 disabled:cursor-not-allowed ${
                      touchedFields.username && fieldErrors.username
                        ? "border-red-500 focus:ring-red-400 focus:border-red-500"
                        : touchedFields.username && username.trim()
                        ? "border-green-500 focus:ring-green-400 focus:border-green-500"
                        : "border-gray-200 dark:border-gray-700 focus:ring-blue-400 focus:border-blue-500"
                    }`}
                    value={username}
                    onChange={(e) => {
                      setUsername(e.target.value);
                      if (touchedFields.username) {
                        setFieldErrors((prev) => ({
                          ...prev,
                          username: undefined,
                        }));
                      }
                    }}
                    onBlur={() => handleFieldBlur("username")}
                    placeholder="Логин"
                    type="text"
                    name="username"
                    autoComplete="username"
                    disabled={isSubmitting}
                    aria-label="Логин"
                    aria-invalid={
                      touchedFields.username && !!fieldErrors.username
                    }
                    aria-describedby={
                      touchedFields.username && fieldErrors.username
                        ? "username-error"
                        : undefined
                    }
                  />
                  {touchedFields.username &&
                    username.trim() &&
                    !fieldErrors.username && (
                      <div className="absolute inset-y-0 right-0 pr-4 flex items-center pointer-events-none">
                        <FaCheckCircle className="text-green-500" size={18} />
                      </div>
                    )}
                </div>
                <AnimatePresence>
                  {touchedFields.username && fieldErrors.username && (
                    <motion.p
                      id="username-error"
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      className="mt-1 text-sm text-red-600 dark:text-red-400"
                    >
                      {fieldErrors.username}
                    </motion.p>
                  )}
                </AnimatePresence>
              </div>

              <div>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                    <FaLock
                      className="text-gray-400 dark:text-gray-500"
                      size={18}
                    />
                  </div>
                  <input
                    className={`w-full pl-12 pr-12 py-3 text-base border dark:bg-gray-800 rounded-lg focus:outline-none focus:ring-2 transition-all duration-300 text-gray-900 dark:text-gray-100 disabled:opacity-50 disabled:cursor-not-allowed ${
                      touchedFields.password && fieldErrors.password
                        ? "border-red-500 focus:ring-red-400 focus:border-red-500"
                        : touchedFields.password &&
                          password &&
                          !fieldErrors.password
                        ? "border-green-500 focus:ring-green-400 focus:border-green-500"
                        : "border-gray-200 dark:border-gray-700 focus:ring-blue-400 focus:border-blue-500"
                    }`}
                    value={password}
                    onChange={(e) => {
                      setPassword(e.target.value);
                      if (touchedFields.password) {
                        setFieldErrors((prev) => ({
                          ...prev,
                          password: undefined,
                        }));
                      }
                    }}
                    onBlur={() => handleFieldBlur("password")}
                    onKeyDown={handleKeyPress}
                    placeholder="Пароль"
                    type={showPassword ? "text" : "password"}
                    name="password"
                    autoComplete="current-password"
                    disabled={isSubmitting}
                    aria-label="Пароль"
                    aria-invalid={
                      touchedFields.password && !!fieldErrors.password
                    }
                    aria-describedby={
                      touchedFields.password && fieldErrors.password
                        ? "password-error"
                        : undefined
                    }
                  />
                  <button
                    type="button"
                    className="absolute top-1/2 right-3 transform -translate-y-1/2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 transition-colors duration-200 p-1 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700"
                    onClick={() => setShowPassword(!showPassword)}
                    tabIndex={-1}
                    disabled={isSubmitting}
                    aria-label={
                      showPassword ? "Скрыть пароль" : "Показать пароль"
                    }
                  >
                    {showPassword ? (
                      <FaEyeSlash size={18} />
                    ) : (
                      <FaEye size={18} />
                    )}
                  </button>
                  {touchedFields.password &&
                    password &&
                    !fieldErrors.password && (
                      <div className="absolute inset-y-0 right-10 pr-4 flex items-center pointer-events-none">
                        <FaCheckCircle className="text-green-500" size={18} />
                      </div>
                    )}
                </div>
                <AnimatePresence>
                  {touchedFields.password && fieldErrors.password && (
                    <motion.p
                      id="password-error"
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      className="mt-1 text-sm text-red-600 dark:text-red-400"
                    >
                      {fieldErrors.password}
                    </motion.p>
                  )}
                </AnimatePresence>
              </div>
            </div>
            <motion.button
              type="submit"
              disabled={isSubmitting || isSuccess}
              className="btn-primary w-full mt-6 py-3.5 flex items-center justify-center gap-2 text-base font-semibold disabled:opacity-70 disabled:cursor-not-allowed"
              whileHover={
                isSubmitting || isSuccess ? {} : { scale: 1.02, y: -1 }
              }
              whileTap={isSubmitting || isSuccess ? {} : { scale: 0.98 }}
              animate={
                isSubmitting
                  ? { opacity: [1, 0.8, 1] }
                  : isSuccess
                  ? { scale: [1, 1.05, 1] }
                  : {}
              }
              transition={{ duration: 0.3 }}
            >
              {isSuccess ? (
                <>
                  <motion.div
                    variants={successVariants}
                    initial="hidden"
                    animate="visible"
                  >
                    <FaCheckCircle size={20} />
                  </motion.div>
                  <span>Успешно!</span>
                </>
              ) : isSubmitting ? (
                <>
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{
                      duration: 1,
                      repeat: Infinity,
                      ease: "linear",
                    }}
                  >
                    <FaSpinner size={20} />
                  </motion.div>
                  <span>Вход...</span>
                </>
              ) : (
                <>
                  <FaSignInAlt size={20} />
                  <span>Войти</span>
                </>
              )}
            </motion.button>
          </motion.form>
          <motion.div variants={itemVariants} className="relative z-10">
            <AnimatePresence>
              {loginError && (
                <motion.div
                  className="mt-4 flex items-center justify-center px-5 py-3 bg-red-500 dark:bg-red-600 text-white rounded-lg text-center font-medium text-sm shadow-lg"
                  variants={errorVariants}
                  initial="hidden"
                  animate="visible"
                  exit="exit"
                >
                  <FaBug className="inline mr-2" size={18} />
                  <span>{loginError}</span>
                </motion.div>
              )}
            </AnimatePresence>

            <motion.div
              className="mt-6 text-center"
              variants={failedAttempts >= 2 ? pulseVariants : undefined}
              initial="initial"
              animate={failedAttempts >= 2 ? "animate" : ""}
            >
              <a
                className="inline-flex items-center text-sm text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 transition-colors duration-300 hover:underline"
                href={`${apiUrl}/password-reset`}
                target="_blank"
                rel="noopener noreferrer"
              >
                Забыли пароль?
              </a>
            </motion.div>
          </motion.div>
        </motion.div>
      </div>
    </div>
  );
};

export default LoginPage;
