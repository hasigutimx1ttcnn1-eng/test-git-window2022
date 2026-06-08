import jpholiday
import difflib
import json
import re
import threading
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Case, When, Value, IntegerField
from django.core.paginator import Paginator
from django.db import transaction
from django.db import models
from .models import MedicalSociety, UserProfile, UpdateHistory, MonitoringURL
from .utils import get_site_content

# --- 補助関数 ---

def fetch_initial_data_async(site_id):
    """
    バックグラウンドで初期データを取得。
    PDFはハッシュ値の取得を優先し、解析負荷を最小限に抑えます。
    """
    try:
        site = MedicalSociety.objects.get(id=site_id)
        for url_obj in site.urls.all():
            try:
                # get_site_content側で「PDFのハッシュ取得」までを行う軽量モードを想定
                # 現状の仕様でも、ここを非同期にすることで画面のフリーズは回避されます
                text, pdfs, new_hash = get_site_content(url_obj.url)
                if new_hash:
                    url_obj.current_text = text
                    url_obj.old_text = text
                    url_obj.pdf_links = pdfs  # ここにPDFのURLとハッシュが含まれる
                    url_obj.save()
            except Exception as e:
                print(f"URL取得エラー (ID:{url_obj.id}): {e}")
    except Exception as e:
        print(f"非同期初期データ取得エラー: {e}")

def get_lookback_hours():
    now = timezone.now()
    hours = 24
    check_date = now - timedelta(days=1)
    while check_date.weekday() >= 5 or jpholiday.is_holiday(check_date):
        hours += 24
        check_date -= timedelta(days=1)
        if hours >= 168: break
    return hours

def get_user_profile(user):
    if not user.is_authenticated: return None
    profile = getattr(user, 'profile', getattr(user, 'userprofile', None))
    if not profile and user.is_superuser:
        profile, _ = UserProfile.objects.get_or_create(
            user=user, 
            defaults={'section_name': 'システム部', 'role': 'SYSTEM_ADMIN'}
        )
    return profile

def clean_text(text):
    if not text: return ""
    text = text.replace('\u200b', '').strip()
    text = re.sub(r'\n+', '\n', text)
    return text

def get_diff_text(old_text, new_text):
    if not old_text or not new_text or old_text == new_text: return ""
    old_lines = (old_text or "").splitlines()
    new_lines = (new_text or "").splitlines()
    diff = difflib.unified_diff(old_lines, new_lines, n=0, lineterm='')
    additions = [line[1:].strip() for line in diff if line.startswith('+') and not line.startswith('+++')]
    return clean_text("\n".join(additions[:10]))

def prepare_items(qs):
    lookback_hours = get_lookback_hours()
    threshold = timezone.now() - timedelta(hours=lookback_hours)
    
    for item in qs:
        # 1. 差分テキストの取得
        all_diffs = []
        for url_obj in item.urls.all():
            diff = get_diff_text(url_obj.old_text, url_obj.current_text)
            if diff:
                label = url_obj.label if url_obj.label else url_obj.url
                all_diffs.append(f"【{label}】\n{diff}")
        
        combined_diff_text = "\n\n".join(all_diffs)
        item.diff_display = combined_diff_text
        
        # 2. 直近の有効な履歴があるか
        valid_histories = item.histories.exclude(snippet__icontains="最新の更新内容はありません").filter(detected_at__gt=threshold)
        item.is_recent = valid_histories.exists() or bool(combined_diff_text.strip())

        # 3. 【修正】黄色タグ判定の厳格化
        # 条件1: テキスト内に「ガイドライン」がある（これがあれば無条件で出す）
        has_guideline_word = "ガイドライン" in combined_diff_text
        
        # 条件2: 履歴にPDF更新がある場合、その対象URLが本当に .pdf で終わっているかを確認
        # これにより、日本性感染症学会のような「偽PDF判定」を完全に弾きます
        has_actual_pdf_update = False
        pdf_histories = valid_histories.filter(update_type__icontains="PDF")
        for h in pdf_histories:
            if h.url_info and h.url_info.url.lower().split('?')[0].endswith('.pdf'):
                has_actual_pdf_update = True
                break

        # 最終判定（変数名をテンプレートに合わせて ribbon に）
        item.show_guideline_ribbon = item.is_recent and (has_guideline_word or has_actual_pdf_update)

        # 4. リンク先設定
        latest_log = valid_histories.order_by('-detected_at').first()
        if item.is_recent and latest_log and latest_log.url_info:
            item.final_url = latest_log.url_info.url
        else:
            item.final_url = item.urls.first().url if item.urls.exists() else "#"
            
        item.latest_log = item.histories.order_by('-detected_at').first()
        
    return qs

@login_required
def dashboard(request):
    profile = get_user_profile(request.user)
    if not profile: 
        return render(request, '403.html', status=403)
    
    is_privileged = (request.user.is_superuser or profile.role == 'SYSTEM_ADMIN' or profile.section_name == 'システム部')
    now = timezone.now()
    threshold = now - timedelta(hours=get_lookback_hours())
    base_query = MedicalSociety.objects.all().prefetch_related('urls', 'histories')

    def get_sorted_query(qs):
        # Orderフィールドを優先して表示順を固定化
        return qs.order_by('order', 'name')

    # 各カテゴリーのデータを取得し、prepare_itemsでフラグをセット
    if is_privileged:
        societies = prepare_items(get_sorted_query(base_query.filter(category='SOCIETY')))
        companies = prepare_items(get_sorted_query(base_query.filter(category='COMPANY')))
    elif profile.section_name == '制作部':
        societies = prepare_items(get_sorted_query(base_query.filter(category='SOCIETY')))
        companies = MedicalSociety.objects.none()
    else:
        societies = MedicalSociety.objects.none()
        companies = prepare_items(get_sorted_query(base_query.filter(category='COMPANY')))

    def _weekly_sort_key(item):
        return (-item.updated_at.date().toordinal(), item.order)

    weekly_com = sorted([item for item in companies if item.is_recent], key=_weekly_sort_key)
    weekly_society = sorted([item for item in societies if item.is_recent], key=_weekly_sort_key)

    guideline_items = [
        {
            'id': item.id,
            'name': item.name,
            'ts': (item.latest_log.detected_at.isoformat() if item.latest_log else item.updated_at.isoformat()),
        }
        for item in list(societies) + list(companies)
        if getattr(item, 'show_guideline_ribbon', False)
    ]

    return render(request, 'societies/dashboard.html', {
        'societies': societies,
        'companies': companies,
        'weekly_com': weekly_com,
        'weekly_society': weekly_society,
        'role': profile.role,
        'section': profile.section_name,
        'user': request.user,
        'now': now,
        'guideline_items_json': json.dumps(guideline_items, ensure_ascii=False),
    })

@login_required
def history_list(request):
    """
    履歴アーカイブ画面。
    組織名をクリックすると、変更があったURLを別タブで開くようにリンクを設定。
    """
    profile = get_user_profile(request.user)
    if not profile: return redirect('dashboard')
    is_privileged = (request.user.is_superuser or profile.role == 'SYSTEM_ADMIN' or profile.section_name == 'システム部')
    
    # 検索・フィルタリングのパラメータ取得
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    show_no_change = request.GET.get('show_no_change') == 'on'
    query = request.GET.get('q')

    history_qs = UpdateHistory.objects.select_related('society', 'url_info').all().order_by('-detected_at')
    
    if not is_privileged:
        cat = 'SOCIETY' if profile.section_name == '制作部' else 'COMPANY'
        history_qs = history_qs.filter(society__category=cat)

    if start_date: history_qs = history_qs.filter(detected_at__date__gte=start_date)
    if end_date: history_qs = history_qs.filter(detected_at__date__lte=end_date)
    if query:
        history_qs = history_qs.filter(Q(society__name__icontains=query) | Q(snippet__icontains=query))
    if not show_no_change:
        history_qs = history_qs.exclude(snippet__icontains="最新の更新内容はありません")

    paginator = Paginator(history_qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    for h in page_obj:
        h.is_today = h.detected_at.date() == timezone.now().date()
        h.snippet = clean_text(h.snippet)

    return render(request, 'societies/history_list.html', {
        'history': page_obj,
        'section': profile.section_name,
        'user': request.user,
        'search_query': query or "",
        'start_date': start_date or "",
        'end_date': end_date or "",
        'show_no_change': show_no_change,
        'is_privileged': is_privileged
    })

@login_required
def admin_panel(request):
    profile = get_user_profile(request.user)
    is_privileged = (request.user.is_superuser or profile.role == 'SYSTEM_ADMIN' or profile.section_name == 'システム部')
    if not is_privileged and profile.role != 'ADMIN':
        raise PermissionDenied

    if request.method == "POST":
        try:
            with transaction.atomic():
                if 'reorder_sites' in request.POST:
                    society_ids = request.POST.getlist('ordered_ids_society[]')
                    company_ids = request.POST.getlist('ordered_ids_company[]')
                    for index, pk in enumerate(society_ids, start=1):
                        MedicalSociety.objects.filter(pk=pk).update(order=index)
                    for index, pk in enumerate(company_ids, start=1):
                        MedicalSociety.objects.filter(pk=pk).update(order=index)
                    messages.success(request, '監視サイトの表示順を保存しました。')

                elif 'add_site' in request.POST:
                    new_site = MedicalSociety.objects.create(
                        name=request.POST.get('name'),
                        department=request.POST.get('department'),
                        category=request.POST.get('category')
                    )
                    urls = request.POST.getlist('urls[]')
                    labels = request.POST.getlist('labels[]')
                    for url, label in zip(urls, labels):
                        if url and url.strip():
                            MonitoringURL.objects.create(society=new_site, url=url.strip(), label=label)
                    # 非同期処理でバックグラウンド実行
                    threading.Thread(target=fetch_initial_data_async, args=(new_site.id,)).start()
                    messages.success(request, f"サイト「{new_site.name}」を追加しました。データ取得は裏側で行われます。")

                elif 'edit_site' in request.POST:
                    site = get_object_or_404(MedicalSociety, id=request.POST.get('site_id'))
                    site.name = request.POST.get('name')
                    site.department = request.POST.get('department')
                    site.category = request.POST.get('category')
                    site.save()
                    site.urls.all().delete()
                    urls = request.POST.getlist('urls[]')
                    labels = request.POST.getlist('labels[]')
                    for url, label in zip(urls, labels):
                        if url and url.strip():
                            MonitoringURL.objects.create(society=site, url=url.strip(), label=label)
                    messages.success(request, f"「{site.name}」を更新しました。")

                elif 'add_user' in request.POST:
                    uname = request.POST.get('username')
                    if User.objects.filter(username=uname).exists():
                        messages.error(request, "そのユーザー名は既に使用されています。")
                    else:
                        new_user = User.objects.create_user(username=uname, password=request.POST.get('password'))
                        UserProfile.objects.create(
                            user=new_user, 
                            role=request.POST.get('role'), 
                            section_name=request.POST.get('section_name')
                        )
                        messages.success(request, f"ユーザー {uname} を作成しました。")

                elif 'update_user' in request.POST:
                    target_user = get_object_or_404(User, id=request.POST.get('user_id'))
                    new_pass = request.POST.get('new_password')
                    if new_pass: target_user.set_password(new_pass)
                    target_user.save()
                    t_prof, _ = UserProfile.objects.get_or_create(user=target_user)
                    t_prof.role = request.POST.get('role')
                    t_prof.section_name = request.POST.get('section_name')
                    t_prof.save()
                    messages.success(request, f"ユーザー {target_user.username} を更新しました。")

                elif 'delete_user' in request.POST:
                    target_user = get_object_or_404(User, id=request.POST.get('user_id'))
                    if target_user != request.user:
                        target_user.delete()
                        messages.success(request, "ユーザーを削除しました。")

        except Exception as e:
            messages.error(request, f"エラー: {e}")
        return redirect('admin_panel')

    all_sites = MedicalSociety.objects.all().prefetch_related('urls').order_by('category', 'order', 'name')
    users = User.objects.all().select_related('profile')
    tab_configs = [('society', 'SOCIETY'), ('company', 'COMPANY')]
    
    return render(request, 'societies/admin_panel.html', {
        'all_sites': all_sites, 'users': users, 'role': profile.role, 'section': profile.section_name,
        'tab_configs': tab_configs,
        'role_choices': UserProfile.ROLE_CHOICES, 'section_choices': UserProfile.SECTION_CHOICES
    })

@login_required
def delete_item(request, pk):
    item = get_object_or_404(MedicalSociety, pk=pk)
    item.delete()
    messages.success(request, "削除しました。")
    return redirect('admin_panel')