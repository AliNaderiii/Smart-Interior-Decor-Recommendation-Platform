export interface User {
  id: string;
  email: string;
  full_name: string;
  role: "homeowner" | "designer" | "admin";
  is_active: boolean;
  subscription_active: boolean;
  subscription_plan: string;
}

export interface AuthPayload {
  user: User;
  access_token: string;
  refresh_token: string;
}

export interface QuizAnswers {
  styles: string[];
  color_palette: string[];
  room_width_cm: number;
  room_length_cm: number;
  budget_min_toman: number;
  budget_max_toman: number;
  materials: string[];
  patterns: string[];
  project_id?: string | null;
  client_name?: string;
}

export interface Explanation {
  style_match: number;
  color_match: number;
  budget_fit: number;
  material_match: number;
  pattern_match: number;
  matched_materials: string[];
  summary: string;
}

export interface RecommendedProduct {
  id: string;
  title: string;
  title_fa?: string;
  category: string;
  price_toman: number;
  image_url: string;
  seller_link: string;
  seller_link_ok: boolean | null;
  colors: string[];
  styles: string[];
  materials: string[];
  patterns: string[];
  width_cm: number;
  depth_cm: number;
  height_cm: number;
  description: string;
  final_score: number;
  explanation: Explanation;
  locked?: boolean;
  /** +1 / -1 when this user has already rated the product (V2 Phase 3). */
  feedback?: number;
  is_verified?: boolean;
}

export interface RecommendResult {
  categories: Record<string, RecommendedProduct[]>;
  cached: boolean;
  is_pro: boolean;
}

export interface MoodboardItem {
  product_id: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Moodboard {
  id: string;
  user_id: string;
  title: string;
  quiz_id: string | null;
  items: MoodboardItem[];
  shopping_list: string[];
  products?: Record<string, RecommendedProduct>;
}

export interface Project {
  id: string;
  name: string;
  client_name: string;
  client_email: string;
  notes: string;
  created_at: string;
  quiz_count: number;
  quizzes?: { id: string; client_name: string; styles: string[]; created_at: string }[];
}

export interface AdminProduct extends Omit<RecommendedProduct, "final_score" | "explanation"> {
  room_type: string;
  extraction_confidence: number;
  is_verified: boolean;
}
