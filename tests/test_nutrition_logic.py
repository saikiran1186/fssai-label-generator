import importlib.util
import pathlib
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"
spec = importlib.util.spec_from_file_location("app", APP_PATH)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class NutritionLogicTest(unittest.TestCase):
    def test_added_sugars_allergens_and_sorting(self):
        ingredients = [
            {"name": "Sugar", "key": "sugar", "is_verified": True, "percentage": 15},
            {"name": "Water", "key": "water", "is_verified": True, "percentage": 25},
            {"name": "Milk", "key": "milk", "is_verified": True, "percentage": 20},
            {"name": "Almonds", "key": "almonds", "is_verified": True, "percentage": 20},
            {"name": "Gram Flour", "key": "gram flour", "is_verified": True, "percentage": 20},
        ]

        totals, missing = app.calculate_nutrition_for_ingredients(ingredients)

        self.assertEqual(missing, [])
        self.assertAlmostEqual(totals["calories"], 259.65, places=2)
        self.assertAlmostEqual(totals["protein"], 9.32, places=2)
        self.assertAlmostEqual(totals["carbs"], 31.92, places=2)
        self.assertAlmostEqual(totals["sugar"], 18.88, places=2)
        # Critical regression: added sugars must count added sweeteners only.
        self.assertAlmostEqual(totals["added_sugars"], 15.00, places=2)
        self.assertAlmostEqual(totals["fat"], 11.98, places=2)
        self.assertAlmostEqual(totals["saturated_fat"], 1.32, places=2)
        self.assertAlmostEqual(totals["sodium"], 21.95, places=2)

        allergens = app.detect_allergens([i["key"] for i in ingredients])
        self.assertEqual(allergens, ["Chickpea", "Milk", "Tree Nuts (Almonds)"])

        sorted_names = [i["name"] for i in app.sort_ingredients_for_label(ingredients)]
        self.assertEqual(
            sorted_names,
            ["Water", "Almonds", "Gram Flour", "Milk", "Sugar"],
        )


if __name__ == "__main__":
    unittest.main()
