export class BaseState<T> {
  data: T | null;
  error: string;
  loading: boolean;
  showNotification: boolean;

  constructor(data: T | null = null) {
    this.data = data;
    this.error = "";
    this.loading = true;
    this.showNotification = false;
  }
}
export interface ITokenResponse {
  refresh: string;
  access: string;
  user: {
    username: string;
    is_banned: boolean;
    is_staff: boolean;
    is_super: boolean;
  };
}

export interface IUserDetails {
  user: {
    username: string;
    email: string;
    first_name: string;
    last_name: string;
    date_joined: string;  
    last_login: string | null;  
    phonenumber: string;
    is_banned: boolean;
    last_login_ip: string | null;  
  };
}

export class ExtendedState<T> extends BaseState<T> {
  startDate: string;
  endDate: string;
  oneMonthDataFetched: boolean;

  constructor(data: T | null = null) {
    super(data);
    this.startDate = "";
    this.endDate = "";
    this.oneMonthDataFetched = false;
  }
}

export interface IChildDepartment {
  child_id: string | number;
  name: string;
  date_of_creation: string;
  parent: string | number;
  has_child_departments: boolean;
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

export interface StaffData {
  name: string;
  surname: string;
  positions: string[];
  avatar: string;
  department: string;
  department_id: number;
  attendance: Record<string, AttendanceData>;
  percent_for_period: number;
  contract_type: string | null;
  salary: number | null;
}

export interface AttendanceData {
  first_in: string | null;
  last_out: string | null;
  percent_day: number;
  total_minutes: number;
  is_weekend: boolean;
  is_remote_work: boolean;
  is_absent_approved: boolean;
  absent_reason: string | null;
}

export interface AttendanceStats {
  department_name: string;
  total_staff_count: number;
  present_staff_count: number;
  absent_staff_count: number;
  present_between_9_to_18: number;
  present_data: Array<{
    staff_pin: string;
    name: string;
    individual_percentage: number;
  }>;
  absent_data: Array<{ staff_pin: string; name: string }>;
  data_for_date : string;
}

export interface LocationData {
  name: string;
  address: string;
  lat: number;
  lng: number;
  employees: number;
}
