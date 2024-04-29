import TextField from "@mui/material/TextField";
import { Box, Button } from "@mui/material";
import React from "react";
import { IForm } from "../schemas/IData.ts";

interface IProps {
  postData: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleFileChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  form: IForm;
  handleInputChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  fileSize: number;
  selectedAgentId: number | null;
}

const ContractForm: React.FC<IProps> = ({
  postData,
  handleFileChange,
  form,
  handleInputChange,
  fileSize,
}) => {
  return (
    <>
      <form onSubmit={postData}>
        <Box
          sx={{
            display: "flex",
            flexDirection: "column",
            gap: "5px",
            width: "200px",
          }}>
          <Button variant="contained" component="label">
            Upload File
            <input onChange={handleFileChange} type="file" name="file" hidden />
          </Button>{" "}
          {form.file ? form.file.name : ""}
          <TextField
            value={form.comment}
            onChange={handleInputChange}
            name="comment"
            label="Comment"
            variant="standard"
          />
          <TextField
            value={form.total}
            onChange={handleInputChange}
            name="total"
            label="Total"
            type="number"
            variant="standard"
          />
          {fileSize < 10 * 1024 ? (
            <Button type="submit">Submit</Button>
          ) : (
            <Button disabled type="submit">
              Submit
            </Button>
          )}
        </Box>
      </form>
    </>
  );
};

export default ContractForm;
