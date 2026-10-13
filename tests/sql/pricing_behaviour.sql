begin;
do $$
begin
 assert (select count(*) from public.ai_model_rates where provider='deepseek' and effective_from='2026-10-13')=4;
 assert (select input_usd_per_m=0.30 and cached_input_usd_per_m=0.006 and output_usd_per_m=1.2
   and off_peak_multiplier=0.5 from public.ai_model_rates where provider='deepseek' and model='deepseek-v4-flash' and effective_from='2026-10-13');
 assert not has_function_privilege('anon','public.pricing_schema_readiness()','EXECUTE');
 assert not has_function_privilege('authenticated','public.pricing_schema_readiness()','EXECUTE');
 assert has_function_privilege('service_role','public.pricing_schema_readiness()','EXECUTE');
end $$;
rollback;
