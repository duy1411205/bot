import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Select, Button, Modal, TextInput
import yt_dlp
import asyncio
from datetime import datetime, timedelta, timezone

# --- CẤU HÌNH MÚI GIỜ VIỆT NAM (UTC+7) ---
VN_TZ = timezone(timedelta(hours=7))

# --- CẤU HÌNH BOT ---
TOKEN = "MTU0OTcyMzIzMTg0NDU2NTA1Mg.GzetGA.6Q4JAlKQ007mNaVudr-DTgEyBbOozWIM3WraMI"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
queues = {}

# --- CẤU HÌNH YT-DLP & FFMPEG ---
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'default_search': 'auto',
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

def play_next(guild, channel):
    guild_id = guild.id
    if guild_id in queues and len(queues[guild_id]) > 0:
        song = queues[guild_id].pop(0)
        vc = guild.voice_client

        if vc and vc.is_connected():
            try:
                info = ytdl.extract_info(song['webpage_url'], download=False)
                audio_url = info['url']
                source = discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS)
                vc.play(source, after=lambda e: play_next(guild, channel))
                
                asyncio.run_coroutine_threadsafe(
                    channel.send(f"🎶 Đang phát: **{song['title']}**"), bot.loop
                )
            except Exception as e:
                asyncio.run_coroutine_threadsafe(
                    channel.send(f"❌ Lỗi khi phát nhạc: {e}"), bot.loop
                )
                play_next(guild, channel)


# --- EMBED BẢNG ĐIỀU KHIỂN CHÍNH ---
def get_main_embed():
    embed = discord.Embed(
        title="🎛️ BẢNG ĐIỀU KHIỂN BOT MULTI-FUNCTION",
        description=(
            "**Bấm trực tiếp vào các nút tính năng bên dưới để thao tác:**\n\n"
            "🎵 **Hàng 1 (Nhạc & Voice):** Treo Voice | Phát Nhạc | Dừng/Tiếp | Bỏ Qua | Tắt Nhạc\n"
            "🛠️ **Hàng 2 (Quản Lý Server):** Xóa Tin Nhắn | Xem Avatar | Tạo Role | Cấp Role"
        ),
        color=discord.Color.gold()
    )
    embed.set_footer(text="Hệ thống quản lý Discord All-in-One")
    return embed


# --- POP-UP MODALS ---

class ClearMessagesModal(Modal, title="Xóa Tin Nhắn Theo Khoảng Ngày"):
    start_date_str = TextInput(
        label="Từ ngày (Định dạng: DD/MM/YYYY)", 
        placeholder="Ví dụ: 10/09/2026", 
        required=True
    )
    end_date_str = TextInput(
        label="Đến ngày (Định dạng: DD/MM/YYYY)", 
        placeholder="Ví dụ: 12/09/2026", 
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ Bạn không có quyền Manage Messages!", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        try:
            start_dt = datetime.strptime(self.start_date_str.value.strip(), "%d/%m/%Y").replace(tzinfo=VN_TZ)
            end_dt = datetime.strptime(self.end_date_str.value.strip(), "%d/%m/%Y").replace(tzinfo=VN_TZ) + timedelta(days=1)

            if start_dt >= end_dt:
                return await interaction.followup.send("❌ Ngày bắt đầu phải nhỏ hơn hoặc bằng ngày kết thúc!", ephemeral=True)

            deleted = await interaction.channel.purge(after=start_dt, before=end_dt)

            await interaction.followup.send(
                f"🧹 Đã xóa thành công **{len(deleted)}** tin nhắn từ ngày **{self.start_date_str.value}** đến hết ngày **{self.end_date_str.value}**!",
                ephemeral=True
            )
        except ValueError:
            await interaction.followup.send("❌ Định dạng ngày không hợp lệ! Vui lòng nhập đúng dạng `DD/MM/YYYY`.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Bot không đủ quyền hạn để xóa tin nhắn!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Có lỗi xảy ra: {e}", ephemeral=True)


class PlayMusicModal(Modal, title="Phát Nhạc"):
    query = TextInput(label="Tên bài hát hoặc Link", placeholder="Nhập tên hoặc link tại đây...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.voice:
            return await interaction.followup.send("❌ Bạn phải vào phòng thoại trước!", ephemeral=True)

        vc = interaction.guild.voice_client
        if not vc:
            vc = await interaction.user.voice.channel.connect(reconnect=True)

        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(self.query.value, download=False))
        except Exception:
            return await interaction.followup.send("❌ Không tìm thấy bài hát này!", ephemeral=True)

        if 'entries' in data:
            data = data['entries'][0]

        song_info = {'title': data.get('title', 'Unknown'), 'webpage_url': data.get('webpage_url', self.query.value)}
        guild_id = interaction.guild_id
        if guild_id not in queues:
            queues[guild_id] = []

        if vc.is_playing() or vc.is_paused():
            queues[guild_id].append(song_info)
            await interaction.followup.send(f"➕ Đã thêm vào hàng chờ: **{song_info['title']}**", ephemeral=True)
        else:
            queues[guild_id].append(song_info)
            await interaction.followup.send(f"🔍 Đang phát bài: **{song_info['title']}**", ephemeral=True)
            play_next(interaction.guild, interaction.channel)


class CreateRoleModal(Modal, title="Nhập Thông Tin Role"):
    role_name = TextInput(label="Tên Role", placeholder="Ví dụ: VIP, BQT...", required=True)
    color_hex = TextInput(label="Mã màu HEX", placeholder="Ví dụ: FF0000", default="FFFFFF", required=False)

    def __init__(self, perm_level: str):
        super().__init__()
        self.perm_level = perm_level

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_roles:
            return await interaction.response.send_message("❌ Bạn không có quyền Manage Roles!", ephemeral=True)

        try:
            color = discord.Color(int(self.color_hex.value.replace("#", ""), 16))
        except ValueError:
            return await interaction.response.send_message("❌ Mã màu HEX không hợp lệ!", ephemeral=True)

        perms = discord.Permissions.none()
        if self.perm_level == "admin":
            perms.administrator = True
        elif self.perm_level == "mod":
            perms.update(
                view_channel=True, send_messages=True, embed_links=True, attach_files=True,
                read_message_history=True, manage_messages=True, kick_members=True,
                mute_members=True, deafen_members=True, move_members=True, connect=True, speak=True
            )
        elif self.perm_level == "member":
            perms.update(
                view_channel=True, send_messages=True, embed_links=True, attach_files=True,
                read_message_history=True, connect=True, speak=True, use_voice_activation=True
            )
        elif self.perm_level == "readonly":
            perms.update(view_channel=True, read_message_history=True, send_messages=False, speak=False)

        try:
            role = await interaction.guild.create_role(
                name=self.role_name.value,
                color=color,
                permissions=perms,
                reason=f"Tạo bởi {interaction.user.name}"
            )
            await interaction.response.send_message(
                f"✅ Đã tạo Role **{role.name}** thành công với quyền **{self.perm_level.upper()}**!", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot không đủ quyền hạn để tạo Role!", ephemeral=True)


# --- NÚT QUAY LẠI CHUNG ---

class BackToMenuButton(Button):
    def __init__(self):
        super().__init__(label="⬅️ Quay lại Menu chính", style=discord.ButtonStyle.secondary, row=4)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=get_main_embed(), view=BotControlPanelView())


# --- GIAO DIỆN CON ---

class AvatarView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(BackToMenuButton())

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Chọn thành viên để xem Avatar...", row=0)
    async def select_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        target = select.values[0]
        embed = discord.Embed(title=f"🖼️ Avatar của {target.display_name}", color=discord.Color.blue())
        embed.set_image(url=target.display_avatar.url)
        await interaction.response.edit_message(embed=embed, view=self)


class AddRoleView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.selected_user = None
        self.add_item(BackToMenuButton())

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="1. Chọn thành viên...", row=0)
    async def select_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        self.selected_user = select.values[0]
        embed = discord.Embed(
            title="👑 Cấp Role Cho Thành Viên",
            description=f"Đã chọn thành viên: {self.selected_user.mention}\n👉 Hãy chọn Role ở menu phía dưới!",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="2. Chọn Role cần cấp...", row=1)
    async def select_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        if not interaction.user.guild_permissions.manage_roles:
            return await interaction.response.send_message("❌ Bạn không có quyền Manage Roles!", ephemeral=True)

        if not self.selected_user:
            return await interaction.response.send_message("❌ Vui lòng chọn Thành viên trước ở bước 1!", ephemeral=True)

        role = select.values[0]
        try:
            await self.selected_user.add_roles(role)
            embed = discord.Embed(
                title="✅ Cấp Role Thành Công!",
                description=f"Đã cấp Role **{role.name}** cho {self.selected_user.mention}!",
                color=discord.Color.brand_green()
            )
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot không có quyền trao Role này!", ephemeral=True)


class RolePermissionSelectView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(BackToMenuButton())

    @discord.ui.select(
        placeholder="Chọn cấp độ phân quyền cho Role...",
        options=[
            discord.SelectOption(label="Thành Viên Thường", value="member", description="Xem/gửi tin nhắn, vào voice", emoji="👤"),
            discord.SelectOption(label="Quản Trị Viên (Mod)", value="mod", description="Kick người, xóa tin nhắn, mute voice", emoji="🛡️"),
            discord.SelectOption(label="Toàn Quyền Admin", value="admin", description="Có tất cả quyền Administrator", emoji="👑"),
            discord.SelectOption(label="Chỉ Đọc (Read-Only)", value="readonly", description="Chỉ xem tin nhắn, không chat/nói", emoji="👁️"),
        ],
        row=0
    )
    async def select_perm(self, interaction: discord.Interaction, select: Select):
        await interaction.response.send_modal(CreateRoleModal(perm_level=select.values[0]))


# --- GIAO DIỆN BẢNG ĐIỀU KHIỂN NÚT BẤM (BUTTON GRID) ---

class BotControlPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    # --- HÀNG 1: TÍNH NĂNG NHẠC & VOICE ---

    @discord.ui.button(label="Treo Voice 24/7", style=discord.ButtonStyle.secondary, emoji="🔒", row=0)
    async def btn_join(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.voice:
            return await interaction.followup.send("❌ Bạn cần vào phòng thoại trước!", ephemeral=True)
        channel = interaction.user.voice.channel
        vc = interaction.guild.voice_client
        if vc:
            await vc.move_to(channel)
        else:
            await channel.connect(reconnect=True)
        await interaction.followup.send(f"🔒 Đã treo 24/7 tại phòng: **{channel.name}**", ephemeral=True)

    @discord.ui.button(label="Phát Nhạc", style=discord.ButtonStyle.success, emoji="🎵", row=0)
    async def btn_play(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PlayMusicModal())

    @discord.ui.button(label="Dừng / Tiếp", style=discord.ButtonStyle.primary, emoji="⏯️", row=0)
    async def btn_pause_resume(self, interaction: discord.Interaction, button: Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Đã tạm dừng nhạc!", ephemeral=True)
        elif vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Đã tiếp tục phát nhạc!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Không có bài hát nào đang phát!", ephemeral=True)

    @discord.ui.button(label="Bỏ Qua", style=discord.ButtonStyle.primary, emoji="⏭️", row=0)
    async def btn_next(self, interaction: discord.Interaction, button: Button):
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await interaction.response.send_message("⏭️ Đã chuyển bài kế tiếp!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Không có nhạc đang phát!", ephemeral=True)

    @discord.ui.button(label="Tắt Nhạc", style=discord.ButtonStyle.danger, emoji="⏹️", row=0)
    async def btn_stop(self, interaction: discord.Interaction, button: Button):
        guild_id = interaction.guild_id
        if guild_id in queues:
            queues[guild_id].clear()
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
        await interaction.response.send_message("⏹️ Đã dừng nhạc và xóa danh sách chờ!", ephemeral=True)

    # --- HÀNG 2: TÍNH NĂNG QUẢN LÝ SERVER ---

    @discord.ui.button(label="Xóa Tin Nhắn Ngày", style=discord.ButtonStyle.danger, emoji="🧹", row=1)
    async def btn_clear(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ Bạn không có quyền Manage Messages!", ephemeral=True)
        await interaction.response.send_modal(ClearMessagesModal())

    @discord.ui.button(label="Xem Avatar", style=discord.ButtonStyle.secondary, emoji="🖼️", row=1)
    async def btn_avatar(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(title="🖼️ Xem Avatar Thành Viên", description="Vui lòng chọn người dùng ở danh sách bên dưới:", color=discord.Color.blue())
        await interaction.response.edit_message(embed=embed, view=AvatarView())

    @discord.ui.button(label="Tạo Role Mới", style=discord.ButtonStyle.secondary, emoji="🛠️", row=1)
    async def btn_create_role(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(title="🛠️ Tạo Role & Phân Quyền", description="Bước 1: Vui lòng chọn cấp độ phân quyền cho Role mới:", color=discord.Color.orange())
        await interaction.response.edit_message(embed=embed, view=RolePermissionSelectView())

    @discord.ui.button(label="Cấp Role", style=discord.ButtonStyle.secondary, emoji="👑", row=1)
    async def btn_add_role(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(title="👑 Cấp Role Cho Thành Viên", description="Bước 1: Chọn thành viên cần cấp Role.", color=discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=AddRoleView())


# --- LỆNH KHỞI CHẠY ---

@bot.event
async def on_ready():
    print(f"🤖 Bot {bot.user} đã sẵn sàng hoạt động!")
    try:
        synced = await bot.tree.sync()
        print(f"🔄 Đã đồng bộ {len(synced)} lệnh Slash (/)")
    except Exception as e:
        print(f"❌ Lỗi đồng bộ lệnh: {e}")


@bot.tree.command(name="menu", description="Mở bảng điều khiển Bot với đầy đủ nút bấm")
async def menu(interaction: discord.Interaction):
    await interaction.response.send_message(embed=get_main_embed(), view=BotControlPanelView())


bot.run(TOKEN)