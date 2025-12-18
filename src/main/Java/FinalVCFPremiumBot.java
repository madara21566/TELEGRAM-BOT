// ================= IMPORTS =================
import org.telegram.telegrambots.bots.TelegramLongPollingBot;
import org.telegram.telegrambots.meta.TelegramBotsApi;
import org.telegram.telegrambots.meta.api.methods.GetFile;
import org.telegram.telegrambots.meta.api.methods.send.*;
import org.telegram.telegrambots.meta.api.objects.*;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.InlineKeyboardMarkup;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.buttons.InlineKeyboardButton;
import org.telegram.telegrambots.meta.exceptions.TelegramApiException;
import org.telegram.telegrambots.updatesreceivers.DefaultBotSession;

import java.io.*;
import java.net.URL;
import java.nio.file.*;
import java.sql.*;
import java.time.*;
import java.util.*;
import java.util.regex.*;

// ================= BOT =================
public class FinalVCFPremiumBot extends TelegramLongPollingBot {

    // ========== ENV ==========
    private final String BOT_TOKEN = System.getenv("BOT_TOKEN");
    private final String BOT_USERNAME = System.getenv("BOT_USERNAME");
    private final long OWNER_ID = Long.parseLong(System.getenv("OWNER_ID"));

    private Connection db;

    // ========== STATES ==========
    private final Map<Long, Boolean> waitingRedeem = new HashMap<>();
    private boolean waitingBroadcastText = false;
    private boolean waitingBroadcastPhoto = false;

    // ========== VCF USER SETTINGS ==========
    private final Map<Long,String> fileNames = new HashMap<>();
    private final Map<Long,String> contactNames = new HashMap<>();
    private final Map<Long,Integer> limits = new HashMap<>();
    private final Map<Long,String> countryCodes = new HashMap<>();
    private final Map<Long,List<File>> mergeQueue = new HashMap<>();

    // ========== INIT ==========
    public FinalVCFPremiumBot() {
        try {
            db = DriverManager.getConnection(
                System.getenv("DB_URL"),
                System.getenv("DB_USER"),
                System.getenv("DB_PASS")
            );

            // auto-expire premium
            new Timer().schedule(new TimerTask() {
                public void run() {
                    try {
                        db.prepareStatement(
                          "UPDATE users SET is_premium=false " +
                          "WHERE premium_expires IS NOT NULL AND premium_expires < NOW()"
                        ).execute();
                    } catch (Exception ignored) {}
                }
            }, 60000, 60000);

        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    // ========== BOT INFO ==========
    @Override public String getBotUsername(){ return BOT_USERNAME; }
    @Override public String getBotToken(){ return BOT_TOKEN; }

    // ========== UPDATE ==========
    @Override
    public void onUpdateReceived(Update u) {
        try {
            if (u.hasMessage()) handleMessage(u.getMessage());
            if (u.hasCallbackQuery()) handleCallback(u.getCallbackQuery());
        } catch (Exception e) {
            logError(e);
        }
    }

    // ========== MESSAGE ==========
    private void handleMessage(Message m) throws Exception {
        long uid = m.getFrom().getId();
        long chatId = m.getChatId();
        saveUser(uid, m.getFrom().getUserName());

        if (isBlocked(uid)) return;

        // /start
        if (m.hasText() && m.getText().equals("/start")) {
            if (uid == OWNER_ID) {
                send(chatId,"👑 ADMIN PANEL", adminKeyboard());
            } else if (isPremium(uid)) {
                send(chatId, vcfHelp());
            } else {
                send(chatId, accessDenied(), redeemKeyboard());
            }
            return;
        }

        // redeem key input
        if (waitingRedeem.getOrDefault(uid,false) && m.hasText()) {
            boolean ok = redeemKey(m.getText().trim(), uid);
            waitingRedeem.remove(uid);
            send(chatId, ok ? "✅ Premium Activated" : "❌ Invalid / Expired Key");
            return;
        }

        // broadcast text
        if (waitingBroadcastText && uid==OWNER_ID && m.hasText()) {
            broadcastText(m.getText());
            waitingBroadcastText=false;
            send(chatId,"✅ Broadcast sent");
            return;
        }

        // broadcast photo
        if (waitingBroadcastPhoto && uid==OWNER_ID && m.hasPhoto()) {
            broadcastPhoto(m);
            waitingBroadcastPhoto=false;
            send(chatId,"✅ Photo broadcast sent");
            return;
        }

        // premium required below
        if (!isPremium(uid)) return;

        // commands
        if (m.hasText()) {
            String t = m.getText();

            if (t.startsWith("/setfilename")) {
                fileNames.put(uid, t.replace("/setfilename","").trim());
                send(chatId,"✅ File name set");
                return;
            }
            if (t.startsWith("/setcontactname")) {
                contactNames.put(uid, t.replace("/setcontactname","").trim());
                send(chatId,"✅ Contact name set");
                return;
            }
            if (t.startsWith("/setlimit")) {
                limits.put(uid, Integer.parseInt(t.split(" ")[1]));
                send(chatId,"✅ Limit set");
                return;
            }
            if (t.startsWith("/setcountrycode")) {
                countryCodes.put(uid, t.split(" ")[1]);
                send(chatId,"✅ Country code set");
                return;
            }
            if (t.startsWith("/merge")) {
                mergeQueue.put(uid,new ArrayList<>());
                send(chatId,"📂 Send VCF files, then /done");
                return;
            }
            if (t.startsWith("/done")) {
                List<File> fs = mergeQueue.get(uid);
                if (fs==null || fs.isEmpty()) {
                    send(chatId,"❌ No files");
                    return;
                }
                File merged = mergeVCF(fs);
                sendFile(chatId, merged);
                merged.delete();
                fs.forEach(File::delete);
                mergeQueue.remove(uid);
                return;
            }

            // numbers to vcf
            List<String> nums = extractNumbers(t);
            if (!nums.isEmpty()) {
                File vcf = generateVCF(uid, nums);
                sendFile(chatId, vcf);
                vcf.delete();
            }
        }

        // documents
        if (m.hasDocument()) handleDocument(m);
    }

    // ========== CALLBACK ==========
    private void handleCallback(CallbackQuery q) throws Exception {
        long uid = q.getFrom().getId();
        String d = q.getData();

        if (d.equals("REDEEM")) {
            waitingRedeem.put(uid,true);
            send(uid,"🔑 Send your premium key:");
            return;
        }

        if (uid != OWNER_ID) return;

        if (d.startsWith("KEY_")) {
            send(uid,"🔐 KEY:\n"+createKey(d.replace("KEY_","")));
        }
        if (d.equals("USERS")) send(uid,getUsers());
        if (d.equals("BC_TEXT")) { waitingBroadcastText=true; send(uid,"Send text"); }
        if (d.equals("BC_PHOTO")) { waitingBroadcastPhoto=true; send(uid,"Send photo"); }
    }

    // ========== VCF ==========
    private File generateVCF(long uid,List<String> nums) throws Exception {
        String base = fileNames.getOrDefault(uid,"Contacts");
        String cname = contactNames.getOrDefault(uid,"Contact");
        int limit = limits.getOrDefault(uid,100);
        String cc = countryCodes.getOrDefault(uid,"");

        File f = new File(base+".vcf");
        StringBuilder sb = new StringBuilder();
        int i=1;
        for (String n:nums) {
            if (i>limit) break;
            sb.append("BEGIN:VCARD\nVERSION:3.0\nFN:")
              .append(cname).append(String.format("%03d",i))
              .append("\nTEL;TYPE=CELL:")
              .append(cc).append(n)
              .append("\nEND:VCARD\n");
            i++;
        }
        Files.write(f.toPath(), sb.toString().getBytes());
        return f;
    }

    private File mergeVCF(List<File> fs) throws Exception {
        File f = new File("merged.vcf");
        StringBuilder sb = new StringBuilder();
        for (File x:fs) sb.append(Files.readString(x.toPath()));
        Files.write(f.toPath(),sb.toString().getBytes());
        return f;
    }

    private void handleDocument(Message m) throws Exception {
        long uid = m.getFrom().getId();
        long chatId = m.getChatId();
        File file = downloadFile(m.getDocument());

        if (mergeQueue.containsKey(uid)) {
            mergeQueue.get(uid).add(file);
            send(chatId,"📥 Added");
            return;
        }

        if (file.getName().endsWith(".vcf")) {
            Set<String> nums = extractFromVCF(file);
            File vcf = generateVCF(uid,new ArrayList<>(nums));
            sendFile(chatId,vcf);
            vcf.delete();
        }

        if (file.getName().endsWith(".txt")) {
            List<String> nums = Files.readAllLines(file.toPath());
            File vcf = generateVCF(uid,nums);
            sendFile(chatId,vcf);
            vcf.delete();
        }

        file.delete();
    }

    // ========== DB ==========
    private void saveUser(long id,String u)throws Exception{
        PreparedStatement ps=db.prepareStatement(
          "INSERT INTO users(id,username) VALUES(?,?) ON CONFLICT(id) DO NOTHING");
        ps.setLong(1,id); ps.setString(2,u); ps.execute();
    }

    private boolean isPremium(long id)throws Exception{
        PreparedStatement ps=db.prepareStatement(
          "SELECT is_premium,premium_expires FROM users WHERE id=?");
        ps.setLong(1,id);
        ResultSet r=ps.executeQuery();
        if(!r.next()) return false;
        Timestamp t=r.getTimestamp(2);
        return r.getBoolean(1)&&(t==null||t.after(new Timestamp(System.currentTimeMillis())));
    }

    private boolean isBlocked(long id)throws Exception{
        PreparedStatement ps=db.prepareStatement(
          "SELECT is_blocked FROM users WHERE id=?");
        ps.setLong(1,id);
        ResultSet r=ps.executeQuery();
        return r.next()&&r.getBoolean(1);
    }

    private boolean redeemKey(String key,long uid)throws Exception{
        PreparedStatement ps=db.prepareStatement(
          "SELECT expires_at FROM keys WHERE key=? AND status='ACTIVE'");
        ps.setString(1,key);
        ResultSet r=ps.executeQuery();
        if(!r.next()) return false;
        Timestamp exp=r.getTimestamp(1);
        if(exp!=null && exp.before(new Timestamp(System.currentTimeMillis()))) return false;

        db.prepareStatement(
          "UPDATE keys SET status='USED',used_by="+uid+" WHERE key='"+key+"'").execute();

        PreparedStatement up=db.prepareStatement(
          "UPDATE users SET is_premium=true,premium_expires=? WHERE id=?");
        up.setTimestamp(1,exp); up.setLong(2,uid); up.execute();
        return true;
    }

    private String createKey(String d)throws Exception{
        String k=UUID.randomUUID().toString().replace("-","").substring(0,16);
        Timestamp exp=null;
        long now=System.currentTimeMillis();
        if(!d.equals("PERMANENT")){
            if(d.equals("1MIN")) exp=new Timestamp(now+60000);
            if(d.equals("1HOUR")) exp=new Timestamp(now+3600000);
            if(d.equals("1MONTH")) exp=new Timestamp(now+2592000000L);
            if(d.equals("2MONTH")) exp=new Timestamp(now+5184000000L);
            if(d.equals("1YEAR")) exp=new Timestamp(now+31536000000L);
        }
        PreparedStatement ps=db.prepareStatement(
          "INSERT INTO keys(key,duration,expires_at,status) VALUES(?,?,?,?)");
        ps.setString(1,k); ps.setString(2,d);
        ps.setTimestamp(3,exp); ps.setString(4,"ACTIVE");
        ps.execute();
        return k;
    }

    private String getUsers()throws Exception{
        StringBuilder sb=new StringBuilder("👥 USERS:\n");
        ResultSet r=db.prepareStatement("SELECT id,is_premium FROM users").executeQuery();
        while(r.next())
            sb.append(r.getLong(1)).append(" | ")
              .append(r.getBoolean(2)?"PREMIUM":"FREE").append("\n");
        return sb.toString();
    }

    // ========== BROADCAST ==========
    private void broadcastText(String t)throws Exception{
        ResultSet r=db.prepareStatement("SELECT id FROM users").executeQuery();
        while(r.next()) send(r.getLong(1),t);
    }

    private void broadcastPhoto(Message m)throws Exception{
        ResultSet r=db.prepareStatement("SELECT id FROM users").executeQuery();
        while(r.next()){
            execute(SendPhoto.builder()
              .chatId(r.getLong(1))
              .photo(new InputFile(m.getPhoto().get(0).getFileId()))
              .caption(m.getCaption()).build());
        }
    }

    // ========== HELPERS ==========
    private Set<String> extractFromVCF(File f)throws Exception{
        Set<String> nums=new HashSet<>();
        Matcher m=Pattern.compile("\\d{7,}").matcher(Files.readString(f.toPath()));
        while(m.find()) nums.add(m.group());
        return nums;
    }

    private List<String> extractNumbers(String t){
        List<String> nums=new ArrayList<>();
        Matcher m=Pattern.compile("\\d{7,}").matcher(t);
        while(m.find()) nums.add(m.group());
        return nums;
    }

    private File downloadFile(Document d)throws Exception{
        GetFile gf=new GetFile(d.getFileId());
        org.telegram.telegrambots.meta.api.objects.File tf=execute(gf);
        File out=new File(d.getFileName());
        try(InputStream is=new URL(tf.getFileUrl(BOT_TOKEN)).openStream()){
            Files.copy(is,out.toPath(),StandardCopyOption.REPLACE_EXISTING);
        }
        return out;
    }

    private void send(long id,String t)throws TelegramApiException{
        execute(new SendMessage(String.valueOf(id),t));
    }
    private void send(long id,String t,InlineKeyboardMarkup k)throws TelegramApiException{
        SendMessage sm=new SendMessage(String.valueOf(id),t);
        sm.setReplyMarkup(k);
        execute(sm);
    }
    private void sendFile(long id,File f)throws TelegramApiException{
        SendDocument sd=new SendDocument();
        sd.setChatId(id);
        sd.setDocument(new InputFile(f));
        execute(sd);
    }

    private InlineKeyboardMarkup adminKeyboard(){
        return new InlineKeyboardMarkup(List.of(
            List.of(btn("🔑 1M","KEY_1MONTH"),btn("🔑 1Y","KEY_1YEAR")),
            List.of(btn("♾ PERM","KEY_PERMANENT")),
            List.of(btn("👥 USERS","USERS")),
            List.of(btn("📢 TEXT BC","BC_TEXT"),btn("📷 PHOTO BC","BC_PHOTO"))
        ));
    }

    private InlineKeyboardMarkup redeemKeyboard(){
        return new InlineKeyboardMarkup(
          List.of(List.of(btn("🔑 Redeem Key","REDEEM"))));
    }

    private InlineKeyboardButton btn(String t,String d){
        InlineKeyboardButton b=new InlineKeyboardButton();
        b.setText(t); b.setCallbackData(d); return b;
    }

    private String accessDenied(){
        return "❌ Access denied\n\n📂💾 VCF Bot Access\nDM @MADARAXHEREE";
    }
    private String vcfHelp(){
        return "✅ VCF BOT ACTIVE\nSend numbers / TXT / VCF";
    }

    private void logError(Exception e){
        try(FileWriter fw=new FileWriter("bot_errors.log",true)){
            fw.write(e.toString()+"\n");
        }catch(Exception ignored){}
    }

    // ========== MAIN ==========
    public static void main(String[] args)throws Exception{
        TelegramBotsApi api=new TelegramBotsApi(DefaultBotSession.class);
        api.registerBot(new FinalVCFPremiumBot());
        System.out.println("🚀 Final Java VCF Premium Bot Running...");
    }
}
