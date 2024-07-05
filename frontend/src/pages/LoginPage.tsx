import { useState } from "react";
import axiosInstance from "../api";
import Cookies from "js-cookie";
import { useNavigate } from "../RouterUtils";
import { FaEye, FaEyeSlash } from "react-icons/fa";

const LoginPage = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
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
    } catch (error) {
      console.error("Login error:", error);
    }
  };

  const handleKeyPress = (e: any) => {
    if (e.key === "Enter") {
      handleSubmit();
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-50">
      <div
        className="w-full max-w-md p-8 space-y-6 bg-white rounded-lg shadow-lg md:max-w-lg lg:max-w-xl xl:max-w-2xl"
        style={{ marginTop: "-25%" }}
      >
        <h2 className="text-3xl font-bold text-center text-gray-800">Login</h2>
        <input
          className="w-full px-4 py-2 mb-4 text-lg bg-gray-100 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          name="username"
          placeholder="Username"
          type="text"
        />
        <div className="relative w-full">
          <input
            className="w-full px-4 py-2 mb-4 text-lg bg-gray-100 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 pr-10"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            name="password"
            placeholder="Password"
            type={showPassword ? "text" : "password"}
            onKeyPress={handleKeyPress}
          />
          <button
            type="button"
            className="absolute inset-y-0 right-0 flex items-center justify-center mb-3 px-3 text-gray-600"
            onClick={() => setShowPassword(!showPassword)}
          >
            {showPassword ? <FaEyeSlash size={24} /> : <FaEye size={24} />}
          </button>
        </div>
        <button
          className="w-full px-4 py-2 text-lg font-semibold text-white bg-blue-500 rounded-md hover:bg-blue-600 focus:outline-none focus:bg-blue-600"
          onClick={handleSubmit}
        >
          Login
        </button>
      </div>
    </div>
  );
};
export default LoginPage;
