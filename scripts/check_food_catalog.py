"""Read-only live diagnostic; bypass the local catalogue cache, never import."""
import argparse
import json
from repository import BusinessError
from services.food_facts_service import browse


def main():
    parser = argparse.ArgumentParser(description='只读验证Open Food Facts分类接口，不写业务数据库。')
    parser.add_argument('--category', default='水饮')
    parser.add_argument('--subcategory', default='饮用水')
    args = parser.parse_args()
    try:
        result = browse(args.category, args.subcategory)
    except BusinessError as exc:
        print(json.dumps({'status': 'failed', 'code': exc.code, 'message': str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({'status': 'ok', 'category': args.category, 'subcategory': args.subcategory,
                      'products': [{'code': p['code'], 'name': p.get('product_name_zh') or p.get('product_name')}
                                   for p in result['products']], 'has_next': result['has_next']}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
