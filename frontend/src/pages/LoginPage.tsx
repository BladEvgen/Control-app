import { useState } from "react";
import axiosInstance from "../api";
import Cookies from "js-cookie";
import { useNavigate } from "../RouterUtils";
import { FaEye, FaEyeSlash } from "react-icons/fa";
import { FaBug } from "react-icons/fa6";

const LoginPage = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loginError, setLoginError] = useState("");

  const navigate = useNavigate();

  const handleSubmit = async () => {
    const formattedUsername = username.trim().toLowerCase();

    try {
      const res = await axiosInstance.post("/token/", {
        username: formattedUsername,
        password,
      });

      Cookies.set("access_token", res.data.access, { path: "/" });
      Cookies.set("refresh_token", res.data.refresh, { path: "/" });

      navigate("/");
      window.location.reload();
    } catch (error: any) {
      console.error("Login error:", error);
      if (error.response && error.response.status !== 401) {
        setLoginError("Проверьте правильность введенных вами данных.");
      } else {
        setLoginError("Произошла ошибка, попробуйте еще раз позже.");
      }
    }
    setTimeout(() => {
      setLoginError("");
    }, 7000);
  };

  const handleKeyPress = (e: any) => {
    if (e.key === "Enter") {
      handleSubmit();
    }
  };

  return (
    <div className="flex flex-col min-h-screen bg-background-light dark:bg-background-dark">
      <div className="flex-grow flex flex-col items-center justify-center animate-gradient-to-r from-accent to-primary">
        <div className="w-full max-w-md p-8 space-y-6 bg-white dark:bg-background-dark rounded-lg shadow-lg bg-opacity-80 md:max-w-lg lg:max-w-xl xl:max-w-2xl">
          <h2 className="text-3xl font-bold text-center text-dark-blue dark:text-text-light">
            Login
          </h2>
          <input
            className="w-full px-4 py-2 mb-4 text-lg bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-light dark:focus:ring-primary"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            name="username"
            placeholder="Username"
            type="text"
          />
          <div className="relative w-full">
            <input
              className="w-full px-4 py-2 mb-4 text-lg bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-light dark:focus:ring-primary pr-10"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              name="password"
              placeholder="Password"
              type={showPassword ? "text" : "password"}
              onKeyPress={handleKeyPress}
            />
            <button
              type="button"
              className="absolute top-[0.7rem] right-2 flex items-center justify-center px-3 text-gray-600 dark:text-gray-400"
              onClick={() => setShowPassword(!showPassword)}
            >
              {showPassword ? <FaEyeSlash size={24} /> : <FaEye size={24} />}
            </button>
          </div>
          <button
            className="w-full px-4 py-2 text-lg font-semibold text-white bg-primary dark:bg-primary-dark rounded-md hover:bg-primary-dark dark:hover:bg-darker-blue focus:outline-none focus:bg-primary-dark dark:focus:bg-darker-blue"
            onClick={handleSubmit}
          >
            Login
          </button>
          {loginError && (
            <div className="p-4 bg-red-500 rounded-lg shadow-md flex items-center mt-4">
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
