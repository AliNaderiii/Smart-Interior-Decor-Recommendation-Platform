# Production datasets requested from the client

The repository's six V3 datasets are a sample contract. Before production, provide:

1. **Product Excel/CSV/JSON** — one row per real SKU with stable ID, Persian title, category, room type, current Toman price, seller name, product URL, licensed image URL, length/depth/height in cm, colors, style IDs, materials, description, stock status and last-checked timestamp.
2. **Approved style taxonomy** — Persian/English labels, descriptions, palettes, materials and licensed sample images. IDs must remain stable.
3. **Approved questionnaire** — wording, option order, range limits, validation and analytics consent text.
4. **Approved plans and entitlements** — monthly/yearly prices, tax rules, recommendation/moodboard/project limits and effective date.
5. **Brand/design assets** — logo, licensed product photography, fonts, empty-state illustrations and image usage rights.
6. **Production service configuration** — supplied through the deployment secret manager, never email or Git:
   - Gemini or OpenAI key
   - Arvan/Liara/AWS S3 access and bucket
   - Zarinpal merchant ID and callback domain
   - Resend API key and verified sender domain
   - strong application `SECRET_KEY`
   - Fernet encryption key

## Delivery validation

- UTF-8 Persian text; prices are integer Toman (not Rial).
- Dimensions are positive centimeters and identify length/depth/height unambiguously.
- Style/material IDs belong to the approved taxonomy.
- HTTPS seller and image links; client confirms rights to display images.
- No duplicate stable IDs.
- Include a price/availability update process and owner.

Use `datasets/products_realistic.json` as the field-level example. The expanded 150-row file is demo data and must not be imported as real stock.
