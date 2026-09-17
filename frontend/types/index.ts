export type Job = {
  id: number;
  uuid?: string;
  source: string;
  url: string;
  title: string;
  company: string;
  location: string;
  work_mode: string;
  seniority: string;
  employment_type: string;
  area?: string;
  description: string;
  salary_min?: number | null;
  salary_max?: number | null;
  currency: string;
  published_at?: string | null;
  discovered_at?: string | null;
  date_status?: string;
  status?: string;
  is_dismissed?: boolean;
  alternative_sources?: any[];
  score?: number | null;
  reasoning: string[];
};

