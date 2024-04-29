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
