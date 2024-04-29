import { Box, Typography } from "@mui/material";
import DepartmentPage from "./DepartmentPage";

const MainPage = () => {
  return (
    <Box m={2}>
      <Typography variant="h4" gutterBottom></Typography>
      <DepartmentPage initialId={1} />
    </Box>
  );
};

export default MainPage;
