import { useState, useCallback } from "react";
import axiosInstance, { setCookie } from "../api";
import { useNavigate } from "../RouterUtils";
import { FaEye, FaEyeSlash, FaSignInAlt } from "react-icons/fa";
import { FaBug } from "react-icons/fa6";
import { apiUrl } from "../../apiConfig";
import { motion, AnimatePresence } from "framer-motion";
import { useUserContext } from "../context/UserContext";

const errorVariants = {
  hidden: { opacity: 0, y: -10 },
  visible: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 10 },
};

const pulseVariants = {
  initial: { scale: 1 },
  animate: {
    scale: [1, 1.05, 1],
    transition: { duration: 1.5, repeat: Infinity, ease: "easeInOut" },
  },
};

const LoginPage = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loginError, setLoginError] = useState("");
  const [failedAttempts, setFailedAttempts] = useState(0);
  const { setUser } = useUserContext();

  const navigate = useNavigate();

  const handleSubmit = useCallback(async () => {
    const formattedUsername = username.trim().toLowerCase();
    try {
      const res = await axiosInstance.post(
        "/token/",
        { username: formattedUsername, password },
        { skipAuthInterceptor: true }
      );

      setCookie("access_token", res.data.access, { path: "/" });
      setCookie("refresh_token", res.data.refresh, { path: "/" });
      setFailedAttempts(0);

      if (res.data.user) {
        setUser(res.data.user);
      } else {
        setUser({ id: 0, username: formattedUsername, is_banned: false });
        window.dispatchEvent(new Event("userLoggedIn"));
      }

      navigate("/");
    } catch (error: any) {
      console.error("Login error:", error);
      setLoginError(
        "Ошибка входа. Проверьте введённые данные или попробуйте позже."
      );
      setFailedAttempts((prev) => prev + 1);
      setTimeout(() => {
        setLoginError("");
      }, 5000);
    }
  }, [username, password, navigate, setUser]);

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleSubmit();
    }
  };

  return (
    <div className="flex flex-col min-h-screen">
      <div className="flex-grow flex flex-col items-center justify-center p-4">
        <div className="w-full max-w-3xl p-10 bg-white dark:bg-gray-900 rounded-xl shadow-2xl border border-gray-300 relative overflow-hidden">
          <h2 className="text-3xl font-bold text-center text-gray-800 dark:text-gray-100 mb-6">
            Добро пожаловать!
          </h2>
          <p className="text-center text-gray-600 dark:text-gray-300 mb-6">
            Войдите в свою учётную запись
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSubmit();
            }}
            className="space-y-5"
          >
            <div className="space-y-5">
              <input
                className="w-full px-4 py-3 text-lg border dark:bg-gray-800 border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 transition-all duration-300 text-gray-900 dark:text-gray-100"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Логин"
                type="text"
                name="username"
                autoComplete="username"
              />
              <div className="relative">
                <input
                  className="w-full px-4 py-3 text-lg border dark:bg-gray-800 border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 pr-12 transition-all duration-300 text-gray-900 dark:text-gray-100"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Пароль"
                  type={showPassword ? "text" : "password"}
                  onKeyDown={handleKeyPress}
                  name="password"
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  className="absolute top-1/2 right-3 transform -translate-y-1/2 text-gray-600 hover:text-gray-800 transition-colors duration-300"
                  onClick={() => setShowPassword(!showPassword)}
                  tabIndex={-1}
                >
                  {showPassword ? (
                    <FaEyeSlash className="dark:text-white" size={20} />
                  ) : (
                    <FaEye className="dark:text-white" size={20} />
                  )}
                </button>
              </div>
            </div>
            <button
              type="submit"
              className="w-full mt-8 px-4 py-3 flex items-center justify-center gap-2 text-lg font-semibold text-white bg-blue-500 rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-400 transition-all duration-300 transform hover:scale-105"
            >
              <FaSignInAlt size={20} />
              <span>Войти</span>
            </button>
          </form>
          <AnimatePresence>
            {loginError && (
              <motion.div
                className="mt-4 flex items-center justify-center px-5 py-3 bg-red-500 text-white rounded-md text-center font-medium text-sm"
                variants={errorVariants}
                initial="hidden"
                animate="visible"
                exit="exit"
              >
                <FaBug className="inline mr-2" size={20} />
                <span>{loginError}</span>
              </motion.div>
            )}
          </AnimatePresence>
          <motion.div
            className="mt-4 text-center"
            variants={failedAttempts >= 2 ? pulseVariants : {}}
            initial="initial"
            animate={failedAttempts >= 2 ? "animate" : ""}
          >
            <a
              className="underline text-blue-600 dark:text-blue-300 hover:text-blue-800 dark:hover:text-blue-200 transition-colors duration-300"
              href={`${apiUrl}/password-reset`}
            >
              Забыли пароль?
            </a>
          </motion.div>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
