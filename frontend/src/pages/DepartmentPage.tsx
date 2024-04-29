import { useState, useEffect } from "react";
import { IChildDepartment, IData } from "../schemas/IData";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import {
  Box,
  Typography,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
} from "@mui/material";

const DepartmentTable = ({
  data,
  handleLinkClick,
  handleBackClick,
}: {
  data: IData;
  handleLinkClick: (id: number, parentId: number) => void;
  handleBackClick: () => void;
}) => {
  const sortedChildDepartments = [...data.child_departments].sort((a, b) =>
    a.name.localeCompare(b.name)
  );

  return (
    <>
      <Box display="flex" justifyContent="space-between" alignItems="center">
        <Typography variant="h6">
          Всего сотрудников у отдела: {data.total_staff_count}
        </Typography>
        <Button onClick={handleBackClick} variant="contained">
          Назад
        </Button>
      </Box>
      <TableContainer component={Paper}>
        <Table aria-label="department table">
          <TableHead>
            <TableRow>
              <TableCell>Имя пототдела</TableCell>
              <TableCell>Дата создания</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sortedChildDepartments.map((department: IChildDepartment) => (
              <TableRow key={department.child_id}>
                <TableCell>
                  <a
                    href="#"
                    onClick={() =>
                      handleLinkClick(department.child_id, department.parent)
                    }>
                    {" "}
                    {department.name}
                  </a>
                </TableCell>
                <TableCell>
                  {new Date(department.date_of_creation).toLocaleString()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </>
  );
};

const DepartmentPage = ({ initialId }: { initialId: number }) => {
  const [data, setData] = useState<IData | null>(null);
  const [prevId, setPrevId] = useState<number | null>(null);
  const [prevParentId, setPrevParentId] = useState<number | null>(null);
  const fetchData = async (id: number) => {
    try {
      const res = await axiosInstance.get(`${apiUrl}/api/department/${id}/`);
      setData(res.data);
    } catch (error) {
      console.error(`Error: ${error}`);
    }
  };

  useEffect(() => {
    fetchData(initialId);
  }, [initialId]);

  const handleLinkClick = (id: number, parentId: number) => {
    setPrevId(data ? data.child_departments[0].child_id : null);
    setPrevParentId(parentId);
    fetchData(id);
  };

  const handleBackClick = () => {
    if (prevParentId !== null) {
      fetchData(prevParentId);
    }
  };

  return (
    <Box m={2}>
      {data ? (
        <>
          <Typography variant="h4" gutterBottom>
            {data.name}
          </Typography>
          <DepartmentTable
            data={data}
            handleLinkClick={handleLinkClick}
            handleBackClick={handleBackClick}
          />
        </>
      ) : (
        <div className="fixed inset-0 flex items-center justify-center z-50">
          <div className="loader text-4xl"></div>
          <span>
            Попробуйте перезагрузить страницу, если данные не загрузились
          </span>
        </div>
      )}
    </Box>
  );
};

export default DepartmentPage;
