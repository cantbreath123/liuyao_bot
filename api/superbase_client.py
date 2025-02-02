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
                'user_name': user_name,
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
        current_time = format_timestamp(datetime.now(timezone(timedelta(hours=8))))
        membership_response = supabase.table('user_memberships') \
            .select('tier_id') \
            .eq('user_id', user_id) \
            .eq('status', True) \
            .gte('end_time', current_time) \
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


def format_timestamp(dt: datetime) -> str:
    """格式化datetime为ISO格式字符串"""
    return dt.strftime('%Y-%m-%d %H:%M:%S')


async def get_today_usage_count(user_id: str):
    """获取用户今日已使用次数"""
    try:
        # 获取北京时间（UTC+8）的今天的开始和结束时间
        beijing_tz = timezone(timedelta(hours=8))
        beijing_now = datetime.now(beijing_tz)
        
        # 设置为当天的开始时间 (00:00:00)
        start_time = beijing_now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 设置为当天的结束时间 (23:59:59)
        end_time = start_time + timedelta(days=1, seconds=-1)
        
        response = supabase.table('projects') \
            .select('id') \
            .eq('user_id', user_id) \
            .eq('env', 'prod') \
            .gte('created_at', format_timestamp(start_time)) \
            .lte('created_at', format_timestamp(end_time)) \
            .execute()

        return len(response.data)
    except Exception as e:
        print(f"获取今日使用次数失败: {str(e)}")
        return 0


async def create_project(user_id: str, question: str):
    """创建新的算卦项目记录"""
    try:
        current_time = format_timestamp(datetime.now(timezone(timedelta(hours=8))))
        project_data = {
            'project_id': f'divination_{int(datetime.now().timestamp())}',
            'user_id': user_id,
            'env': 'prod',
            'message_list': [{'role': 'user', 'content': question}],
            'created_at': current_time
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
        current_time = format_timestamp(datetime.now(timezone(timedelta(hours=8))))
        membership_response = supabase.table('user_memberships')\
            .select('tier_id, start_time, end_time')\
            .eq('user_id', user_id)\
            .eq('status', True)\
            .gte('end_time', current_time)\
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


async def create_user_with_membership(user_id: str, user_name: str, tier_id: str):
    """创建用户并分配会员资格"""
    try:
        # 获取会员等级信息
        tier_response = supabase.table('membership_tiers') \
            .select('*') \
            .eq('tier_id', tier_id) \
            .execute()
            
        if not tier_response.data:
            print(f"会员等级不存在: {tier_id}")
            return None
            
        tier_info = tier_response.data[0]
        
        # 计算会员有效期
        beijing_tz = timezone(timedelta(hours=8))
        start_time = datetime.now(beijing_tz)
        
        if tier_info['duration_unit'] == 'MONTH':
            end_time = start_time + timedelta(days=30 * tier_info['duration_amount'])
        elif tier_info['duration_unit'] == 'YEAR':
            end_time = start_time + timedelta(days=365 * tier_info['duration_amount'])
        else:  # 默认按天计算
            end_time = start_time + timedelta(days=tier_info['duration_amount'])
            
        # 创建会员记录
        membership_data = {
            'user_id': user_id,
            'tier_id': tier_id,
            'start_time': format_timestamp(start_time),
            'end_time': format_timestamp(end_time),
            'status': True,
            'env': 'prod'
        }
        
        # 将用户现有会员设为无效
        supabase.table('user_memberships') \
            .update({'status': False}) \
            .eq('user_id', user_id) \
            .eq('status', True) \
            .execute()
            
        # 创建新的会员记录
        membership_response = supabase.table('user_memberships') \
            .insert(membership_data) \
            .execute()
            
        if not membership_response.data:
            print("创建会员记录失败")
            return None
            
        return {
            'user': user_id,
            'membership': membership_response.data[0],
            'tier': tier_info
        }
        
    except Exception as e:
        print(f"创建用户会员失败: {str(e)}")
        return None


if __name__ == '__main__':
    asyncio.run(create_user_with_membership("0cda1975-06fc-4cd8-b28a-1ee64bdfc1e6", "no one", "vip1"))
