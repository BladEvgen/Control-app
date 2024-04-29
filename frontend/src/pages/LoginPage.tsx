import { Box, Button, TextField } from "@mui/material";
import { useState } from "react";
import axiosInstance from "../api";
import Cookies from "js-cookie";
import { useNavigate } from "react-router-dom";

const LoginPage = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const navigate = useNavigate();

  const handleSubmit = async () => {
    try {
      const res = await axiosInstance.post("/token/", {
        username,
        password,
      });

      Cookies.set("access_token", res.data.access, { path: "/" });
      Cookies.set("refresh_token", res.data.refresh, { path: "/" });

      navigate("/");
    } catch (error) {
      console.error("Login error:", error);
    }
  };

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        width: "100%",
        maxWidth: 400,
        margin: "0 auto",
        padding: "20px",
      }}>
      <TextField
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        name="username"
        label="Username"
        type="text"
        variant="standard"
        fullWidth
      />
      <TextField
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        name="password"
        label="Пароль"
        type="password"
        variant="standard"
        fullWidth
      />
      <Button
        variant="contained"
        color="primary"
        onClick={handleSubmit}
        fullWidth>
        Вход
      </Button>
    </Box>
  );
};

export default LoginPage;
