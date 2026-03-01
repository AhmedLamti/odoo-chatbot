from etl.schema_extractor import SchemaExtractor

if __name__ == "__main__":
    extractor = SchemaExtractor()
    schema = extractor.extract()
    print(f"\n✓ Schéma extrait : {len(schema)} tables")
