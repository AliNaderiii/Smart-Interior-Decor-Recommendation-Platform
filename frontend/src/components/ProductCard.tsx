import { memo } from "react";
import type { RecommendedProduct } from "@/lib/types";
import { formatToman } from "@/lib/constants";
import { Badge, Button, Card } from "@/components/ui";

interface Props {
  product: RecommendedProduct;
  rank: number;
  onAdd?: (p: RecommendedProduct) => void;
  added?: boolean;
}

/** Recommendation card with Havenly-style explainability badges. */
function ProductCardInner({ product, rank, onAdd, added }: Props) {
  if (product.locked) {
    return (
      <Card className="relative overflow-hidden">
        <img
          src={product.image_url}
          alt={product.title}
          width={400}
          height={260}
          loading="lazy"
          className="h-40 w-full object-cover blur-md"
        />
        <div className="absolute inset-0 grid place-items-center bg-white/40 p-4 text-center">
          <div>
            <p className="text-sm font-semibold text-walnut">Upgrade to see all matches</p>
            <a href="/upgrade" className="mt-2 inline-block rounded-xl bg-clay px-4 py-2 text-sm font-semibold text-white hover:bg-clay-dark">
              Unlock with Pro
            </a>
          </div>
        </div>
      </Card>
    );
  }

  const exp = product.explanation;
  return (
    <Card className="flex flex-col overflow-hidden">
      <div className="relative">
        <img
          src={product.image_url}
          alt={product.title}
          width={400}
          height={260}
          loading={rank === 0 ? "eager" : "lazy"}
          fetchPriority={rank === 0 ? "high" : undefined}
          className="h-40 w-full object-cover"
        />
        <span className="absolute left-2 top-2 rounded-full bg-white/90 px-2 py-0.5 text-xs font-bold text-walnut">
          #{rank + 1}
        </span>
      </div>
      <div className="flex flex-1 flex-col gap-2 p-4">
        <h3 className="line-clamp-2 text-sm font-semibold leading-snug">{product.title}</h3>
        <p className="font-bold text-clay-dark">{formatToman(product.price_toman)}</p>
        <div className="flex flex-wrap gap-1.5">
          <Badge tone="clay">{exp.style_match}% Style</Badge>
          <Badge tone="success">{exp.color_match}% Color</Badge>
          <Badge>{exp.budget_fit}% Budget</Badge>
          {exp.matched_materials.length > 0 && (
            <Badge tone="warning">Material: {exp.matched_materials.join(", ")}</Badge>
          )}
        </div>
        <p className="text-xs leading-relaxed text-stone">{exp.summary}</p>
        <div className="mt-auto flex items-center gap-2 pt-2">
          {onAdd && (
            <Button
              variant={added ? "secondary" : "primary"}
              className="flex-1 py-2 text-xs"
              onClick={() => onAdd(product)}
              disabled={added}
            >
              {added ? "Added ✓" : "Add to moodboard"}
            </Button>
          )}
          {product.seller_link && (
            <a
              href={product.seller_link}
              target="_blank"
              rel="noreferrer noopener"
              className="rounded-xl bg-sand px-3 py-2 text-xs font-semibold text-walnut hover:bg-[#e8e0d4]"
              aria-label={`Buy ${product.title} from seller`}
            >
              Buy {product.seller_link_ok && <span className="text-sage" title="Link verified">●</span>}
            </a>
          )}
        </div>
      </div>
    </Card>
  );
}

export const ProductCard = memo(ProductCardInner);
