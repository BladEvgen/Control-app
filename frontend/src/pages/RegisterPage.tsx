import { Box, Button, TextField } from "@mui/material";
import { useEffect, useState } from "react";
import axiosInstance from "../api";
import Cookies from "js-cookie";
import { useNavigate } from "react-router-dom";

const RegisterPage = () => {
  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");

  const navigate = useNavigate();

  const handleSubmit = async () => {
    const res = await axiosInstance.post("/user/register/", {
      email: email,
      password: password,
    });
    console.log(res.status);

    if (res.status === 200 || res.status === 201) {
      const username = email.split("@")[0];
      const res = await axiosInstance.post("/token/", {
        username: username,
        password: password,
      });
      console.log("Result", res);

      Cookies.set("access_token", res.data.access, { path: "/" });
      Cookies.set("refresh_token", res.data.refresh, { path: "/" });

      navigate("/");
    }

    console.log(res);
  };

  useEffect(() => {}, []);

  return (
    <>
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          width: "100%",
          maxWidth: "400px",
          margin: "0 auto",
          padding: "20px",
        }}>
        <TextField
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          name="username"
          label="Email"
          type="string"
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
        <Button variant="contained" onClick={handleSubmit} fullWidth>
          Зарегистрироваться
        </Button>
      </Box>
    </>
  );
};

export default RegisterPage;
