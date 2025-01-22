import asyncio
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta
import uuid

url: str = "https://arggsykvbidbocqnjmld.supabase.co"
key: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFyZ2dzeWt2YmlkYm9jcW5qbWxkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Mzc1MzUyMTksImV4cCI6MjA1MzExMTIxOX0.etofAeX3r11BAZzZwXbAgyiO9VUZTwyiL_1dg2ttPq4"
supabase: Client = create_client(url, key)


async def init_base_tier():
    """初始化基础会员等级"""
    try:
        # 检查是否已存在基础会员等级
        response = supabase.table('membership_tiers').select('*').eq('tier_id', 'base').execute()
        if not response.data:
            # 创建基础会员等级
            data = {
                'tier_id': 'base',
                'name': '免费会员',
                'price': 0.00,
                'daily_limit': 1,
                'description': '基础会员每日可免费算卦1次',
                'duration_unit': 'MONTH',
                'duration_amount': 999999,  # 永久有效
                'status': True,
                'env': 'prod'
            }
            data2 = {
                'tier_id': 'vip1-month',
                'name': '基础会员',
                'price': 10.00,
                'daily_limit': 1,
                'description': '基础会员每日可免费算卦1次',
                'duration_unit': 'MONTH',
                'duration_amount': 1,  # 永久有效
                'status': True,
                'env': 'prod'
            }
            supabase.table('membership_tiers').insert(data2).execute()
    except Exception as e:
        print(f"初始化基础会员等级失败: {str(e)}")


async def get_or_create_user(tg_user_id: str, user_name: str):
    """获取或创建用户"""
    try:
        # 检查用户是否存在
        response = supabase.table('users').select('*').eq('tg_user_id', tg_user_id).execute()
        if not response.data:
            # 创建新用户，使用 UUID 作为 user_id
            user_data = {
                'user_id': str(uuid.uuid4()),  # 生成 UUID
                'tg_user_id': tg_user_id,
                'is_valid': True
            }
            response = supabase.table('users').insert(user_data).execute()
            user = response.data[0]
        else:
            user = response.data[0]
        return user
    except Exception as e:
        print(f"获取或创建用户失败: {str(e)}")
        return None


async def get_user_daily_limit(user_id: str):
    """获取用户每日限制次数"""
    try:
        # 1. 获取用户当前有效的会员资格
        now = datetime.now(timezone.utc).isoformat()
        membership_response = supabase.table('user_memberships') \
            .select('tier_id') \
            .eq('user_id', user_id) \
            .eq('status', True) \
            .gte('end_time', now) \
            .execute()

        if not membership_response.data:
            return 1  # 默认限制

        # 2. 获取会员等级的每日限制
        tier_id = membership_response.data[0]['tier_id']
        tier_response = supabase.table('membership_tiers') \
            .select('daily_limit') \
            .eq('tier_id', tier_id) \
            .execute()

        if tier_response.data:
            return tier_response.data[0]['daily_limit']

        return 1  # 默认限制
    except Exception as e:
        print(f"获取用户每日限制失败: {str(e)}")
        return 1  # 出错时返回默认限制


async def get_today_usage_count(user_id: str, current_date: str):
    """获取用户今日已使用次数"""
    try:
        # 获取用户当日的项目记录
        start_time = f"{current_date}T00:00:00Z"
        end_time = f"{current_date}T23:59:59Z"
        response = supabase.table('projects') \
            .select('id') \
            .eq('user_id', user_id) \
            .eq('env', 'prod') \
            .gte('created_at', start_time) \
            .lte('created_at', end_time) \
            .execute()

        return len(response.data)
    except Exception as e:
        print(f"获取今日使用次数失败: {str(e)}")
        return 0


async def create_project(user_id: str, question: str):
    """创建新的算卦项目记录"""
    try:

        project_data = {
            'project_id': f'divination_{datetime.now(timezone.utc).timestamp()}',
            'user_id': user_id,
            'env': 'prod',
            'message_list': [{'role': 'user', 'content': question}]
        }

        response = supabase.table('projects').insert(project_data).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"创建项目记录失败: {str(e)}")
        return None


async def update_project_messages(project_id: str, messages: list):
    """更新项目的消息列表"""
    try:
        supabase.table('projects') \
            .update({'message_list': messages}) \
            .eq('project_id', project_id) \
            .execute()
        return True
    except Exception as e:
        print(f"更新项目消息失败: {str(e)}")
        return False


async def get_user_membership_info(user_id: str):
    """获取用户的会员信息"""
    try:
        # 获取用户当前有效的会员资格
        now = datetime.now(timezone.utc).isoformat()
        membership_response = supabase.table('user_memberships')\
            .select('tier_id, start_time, end_time')\
            .eq('user_id', user_id)\
            .eq('status', True)\
            .gte('end_time', now)\
            .execute()
            
        if not membership_response.data:
            return None
            
        membership = membership_response.data[0]
        
        # 获取会员等级信息
        tier_response = supabase.table('membership_tiers')\
            .select('name, daily_limit, description')\
            .eq('tier_id', membership['tier_id'])\
            .execute()
            
        if tier_response.data:
            tier_info = tier_response.data[0]
            return {
                'tier_name': tier_info['name'],
                'daily_limit': tier_info['daily_limit'],
                'description': tier_info['description'],
                'start_time': membership['start_time'],
                'end_time': membership['end_time']
            }
            
        return None
    except Exception as e:
        print(f"获取用户会员信息失败: {str(e)}")
        return None


if __name__ == '__main__':
    asyncio.run(init_base_tier())
