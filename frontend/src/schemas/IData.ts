export interface IChildDepartment {
  child_id: number;
  name: string;
  date_of_creation: string;
  parent: number;
}

export interface IData {
  name: string;
  date_of_creation: string;
  child_departments: IChildDepartment[];
  total_staff_count: number;
}

export interface IStaffData {
  [key: string]: {
    FIO: string;
    date_of_creation: string;
    avatar: string | null;
    positions: string[];
  };
}
export interface IChildDepartmentData {
  child_department: IChildDepartment;
  staff_count: number;
  staff_data: IStaffData;
}