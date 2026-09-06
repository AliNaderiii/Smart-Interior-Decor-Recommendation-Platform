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
  /** ADR-012 dimensional fit, 0–100; 50 = unknown/neutral. */
  fit_match: number;
  /** Stable reason code the UI localises (fit_ok, fit_tight, fit_too_big, fit_too_small, fit_too_tall, fit_unknown, fit_neutral). */
  fit_reason: FitReason;
  matched_materials: string[];
  summary: string;
}

export type FitReason =
  | "fit_ok"
  | "fit_tight"
  | "fit_too_big"
  | "fit_too_small"
  | "fit_too_tall"
  | "fit_unknown"
  | "fit_neutral";

export interface RecommendedProduct {
  id: string;
  title: string;
  title_fa?: string;
  category: string;
  price_toman: number;
  image_url: string;
  seller_link: string;
  seller_link_ok: boolean | null;
  link_status?: "ok" | "redirect" | "dead" | "unsafe" | "blocked" | string | null;
  link_checked_at?: string | null;
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

/** ADR-013 — one hit from POST /search/visual. Locked teasers carry only
 *  id/title/category/image_url/similarity. */
export interface VisualSearchItem
  extends Partial<Omit<RecommendedProduct, "id" | "title" | "category" | "image_url">> {
  id: string;
  title: string;
  category: string;
  image_url: string;
  /** Blended 0–1 score used for ranking. */
  similarity: number;
  /** Perceptual palette agreement, 0–1 (always present on full items). */
  palette_match?: number;
  /** Cross-modal CLIP cosine, 0–1 — only in `clip` mode. */
  clip_similarity?: number;
  locked?: boolean;
}

export interface VisualSearchResult {
  items: VisualSearchItem[];
  is_pro: boolean;
  meta: {
    /** `clip` = image embedding + palette; `palette` = colour-only (hash backend). */
    mode: "clip" | "palette";
    palette: string[];
    category: string | null;
    candidates: number;
    embedding_backend: string;
    query_image?: { width: number; height: number; content_type: string };
  };
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
  /** Server-side lifecycle (migration 0005), no longer localStorage-derived. */
  status: "draft" | "shared" | "approved" | "completed";
  created_at: string;
  quiz_count: number;
  moodboard_count: number;
  approved_count: number;
  rejected_count: number;
  quizzes?: { id: string; client_name: string; styles: string[]; created_at: string }[];
  moodboards?: { id: string; title: string; item_count: number; created_at: string }[];
  /** Every verdict the client has left, newest first. */
  feedback?: {
    product_id: string;
    title: string;
    title_fa?: string;
    verdict: "approved" | "rejected";
    comment: string;
    updated_at: string;
  }[];
}

export interface AdminProduct extends Omit<RecommendedProduct, "final_score" | "explanation"> {
  room_type: string;
  extraction_confidence: number;
  is_verified: boolean;
}
