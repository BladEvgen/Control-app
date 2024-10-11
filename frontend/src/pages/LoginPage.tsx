import { useState, useCallback } from "react";
import axiosInstance, { setCookie } from "../api";
import { useNavigate } from "../RouterUtils";
import { FaEye, FaEyeSlash, FaInfoCircle } from "react-icons/fa";
import { FaBug } from "react-icons/fa6";
import { apiUrl } from "../../apiConfig";

const LoginPage = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loginError, setLoginError] = useState("");

  const navigate = useNavigate();

  const handleSubmit = useCallback(async () => {
    const formattedUsername = username.trim().toLowerCase();

    try {
      const res = await axiosInstance.post("/token/", {
        username: formattedUsername,
        password,
      });

      setCookie("access_token", res.data.access, { path: "/" });
      setCookie("refresh_token", res.data.refresh, { path: "/" });
      setCookie("username", formattedUsername, { path: "/" });

      navigate("/");
      window.location.reload();
    } catch (error: any) {
      console.error("Login error:", error);
      setLoginError("Ошибка входа. Пожалуйста, попробуйте позже.");
    }
    setTimeout(() => {
      setLoginError("");
    }, 7000);
  }, [username, password, navigate]);

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleSubmit();
    }
  };

  return (
    <div className="flex flex-col min-h-screen bg-footer-light dark:bg-background-dark">
      <div className="flex-grow flex flex-col items-center justify-center bg-gradient-to-b from-primary-dark to-footer-light dark:from-primary-dark dark:to-background-dark py-8 px-4 sm:px-6 lg:px-8">
        <div className="w-full max-w-sm sm:max-w-md md:max-w-lg lg:max-w-xl xl:max-w-2xl p-6 space-y-6 bg-white dark:bg-gray-900 rounded-lg shadow-lg bg-opacity-90">
          <h2 className="text-3xl font-bold text-center text-dark-blue dark:text-text-light mb-4">
            Welcome Back!
          </h2>
          <p className="text-center text-gray-600 dark:text-gray-400">
            Please login to your account
          </p>
          <input
            className="w-full px-4 py-2 mt-4 text-lg bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-light dark:focus:ring-primary transition-all duration-300 ease-in-out"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            name="username"
            placeholder="Username"
            type="text"
          />
          <div className="relative w-full">
            <input
              className="w-full px-4 py-2 mt-4 text-lg bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-light dark:focus:ring-primary pr-10 transition-all duration-300 ease-in-out"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              name="password"
              placeholder="Password"
              type={showPassword ? "text" : "password"}
              onKeyPress={handleKeyPress}
            />
            <button
              type="button"
              className="absolute top-[1.6rem] right-2 flex items-center justify-center px-3 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200"
              onClick={() => setShowPassword(!showPassword)}
            >
              {showPassword ? <FaEyeSlash size={24} /> : <FaEye size={24} />}
            </button>
          </div>
          <button
            className="w-full px-4 py-2 mt-6 text-lg font-semibold text-white bg-primary dark:bg-primary-dark rounded-md hover:bg-primary-dark dark:hover:bg-darker-blue focus:outline-none focus:bg-primary-dark dark:focus:bg-darker-blue transition-all duration-300 ease-in-out transform hover:scale-105"
            onClick={handleSubmit}
          >
            Login
          </button>
          <div className="flex items-center justify-between mt-4">
            <div className="flex items-center text-primary hover:text-blue-600 dark:text-primary-light dark:hover:text-blue-400 transition-colors duration-300 ease-in-out">
              <FaInfoCircle className="mr-2" />
              <a
                className="underline text-lg font-medium"
                href={`${apiUrl}/password-reset`}
              >
                Forgot password?
              </a>
            </div>
          </div>
          {loginError && (
            <div className="p-4 bg-red-500 dark:bg-red-700 rounded-lg shadow-md flex items-center mt-4">
              <div className="mr-2">
                <FaBug className="text-white" size={24} />
              </div>
              <p className="text-lg font-semibold text-white">{loginError}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
