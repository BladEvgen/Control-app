import { useState } from "react";
import axiosInstance from "../api";
import Cookies from "js-cookie";
import { useNavigate } from "../RouterUtils"; 

const LoginPage = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
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
    <div className="flex flex-col items-center justify-center w-full max-w-md mx-auto p-6 bg-gray-100 rounded-lg shadow-md">
      <input
        className="w-full px-4 py-2 mb-4 text-lg bg-gray-200 border border-gray-300 rounded-md focus:outline-none focus:border-blue-500"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        name="username"
        placeholder="Username"
        type="text"
      />
      <input
        className="w-full px-4 py-2 mb-4 text-lg bg-gray-200 border border-gray-300 rounded-md focus:outline-none focus:border-blue-500"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        name="password"
        placeholder="Password"
        type="password"
        onKeyPress={handleKeyPress}
      />
      <button
        className="w-full px-4 py-2 text-lg font-semibold text-white bg-blue-500 rounded-md hover:bg-blue-600 focus:outline-none focus:bg-blue-600"
        onClick={handleSubmit}>
        Login
      </button>
    </div>
  );
};

export default LoginPage;
