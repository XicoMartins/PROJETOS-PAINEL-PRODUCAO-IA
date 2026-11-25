ALTER TABLE public.painting_entries
  ADD COLUMN IF NOT EXISTS fornecedor_pintura text,
  ADD CONSTRAINT painting_entries_fornecedor_pintura_check
    CHECK (fornecedor_pintura IN ('Multipint', 'SCHUNCK', 'Aquapint'));
