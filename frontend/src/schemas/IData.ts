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
  access_token_expires: string;
  refresh_token_expires: string;
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

export interface IBreadcrumbPathItem {
  id: string;
  name: string;
}

export interface IData {
  name: string;
  date_of_creation: string;
  child_departments: IChildDepartment[];
  total_staff_count: number;
  breadcrumb_path?: IBreadcrumbPathItem[];
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
  breadcrumb_path?: IBreadcrumbPathItem[];
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
  bonus_percentage: number;
  contract_type: string | null;
  salary: number | null;
}

export interface AttendanceData {
  first_in: string | null;
  last_out: string | null;
  percent_day: number;
  total_minutes: number;
  effective_work_seconds?: number | null;
  area_sequence?: Array<{ t: string; area: string }> | null;
  is_weekend: boolean;
  is_remote_work: boolean;
  is_absent_approved: boolean;
  absent_reason: string | null;
}

export interface AttendanceStatsPresentItem {
  staff_pin: string;
  name: string;
  minutes_present?: number;
  individual_percentage: number;
}

export interface AttendanceStats {
  department_name: string;
  total_staff_count: number;
  present_staff_count: number;
  absent_staff_count: number;
  present_between_9_to_18?: number;
  present_data: AttendanceStatsPresentItem[];
  absent_data: Array<{ staff_pin: string; name: string }>;
  data_for_date: string;
}

export interface LocationData {
  name: string;
  address: string;
  lat: number;
  lng: number;
  employees: number;
}

export interface PhotoData {
  id?: number;
  hasPhoto?: boolean;
  staffPin: string;
  staffFullName: string;
  department: string;
  photoUrl: string;
  attendanceTime: string;
  tutorInfo: string;
  photoSpoofStatus?: PhotoSpoofStatus;
  photoManualVerdict?: PhotoManualVerdict;
  photoCanSetManualVerdict?: boolean;
  stateCode?: PhotoStateCode;
  versionTs?: string;
  op?: PhotoWsOp;
}

export type PhotoSpoofStatus =
  | "pending"
  | "clean"
  | "review"
  | "suspicious"
  | "error";

export type PhotoManualVerdict = "none" | "clean" | "suspicious";

export type PhotoStateCode =
  | "SNAPSHOT"
  | "CREATED_NO_PHOTO"
  | "PHOTO_ATTACHED"
  | "UPDATED_META"
  | "DELETED";

export type PhotoWsOp = "snapshot" | "created" | "updated" | "deleted";

export interface PhotoWsMessage {
  type?: "initial_photos" | "photos_updated" | "heartbeat" | "ping" | "pong";
  protocol?: string;
  batchId?: string;
  chunkIndex?: number;
  totalChunks?: number;
  sentAt?: string;
  events?: PhotoData[];
  photos?: PhotoData[];
  newPhoto?: PhotoData;
}
